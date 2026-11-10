import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import liff from "@line/liff";
import { resolveAccountId } from "./account";
import { api, setCsrfToken } from "./api";
import { translate } from "./i18n";
import "./styles.css";

const defaultPreferences = {
  language: "zh-TW", interests: [], content_depth: "story", preferred_duration: "1h",
  transportation: "walking", walking_preference: "medium", stay_minutes: 60,
  voice: { speaker: "default", speed: 1, pitch: 0 },
};

const interestOptions = ["sugar", "heritage", "railway", "local_business", "faith", "oral_history", "agriculture", "puppetry"];
const depthOptions = ["quick", "story", "deep", "field"];
const durationOptions = ["30m", "1h", "half_day", "full_day"];

function App() {
  const accountId = resolveAccountId(location.search);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [tab, setTab] = useState("home");
  const [menuOpen, setMenuOpen] = useState(false);
  const [displayName, setDisplayName] = useState("");
  const [pictureUrl, setPictureUrl] = useState("");
  const [preferences, setPreferences] = useState(defaultPreferences);
  const [favorites, setFavorites] = useState([]);
  const [history, setHistory] = useState([]);
  const [puzzle, setPuzzle] = useState({});
  const [linked, setLinked] = useState(false);
  const [favoriteInput, setFavoriteInput] = useState("");
  const [removingFavorite, setRemovingFavorite] = useState("");
  const [actionError, setActionError] = useState("");
  const [savingPreferences, setSavingPreferences] = useState(false);
  const [preferenceMessage, setPreferenceMessage] = useState("");
  const [settingsMessage, setSettingsMessage] = useState("");
  const t = useMemo(() => (key, values) => translate(preferences.language, key, values), [preferences.language]);

  async function refresh() {
    const [profile, favoriteRows, historyRows, puzzleState] = await Promise.all([
      api("/api/me"), api("/api/me/favorites"), api("/api/me/history"), api("/api/me/puzzles"),
    ]);
    setPreferences(profile.preferences || defaultPreferences);
    setLinked(Boolean(profile.linked));
    setFavorites(favoriteRows); setHistory(historyRows); setPuzzle(puzzleState);
  }

  useEffect(() => {
    (async () => {
      try {
        const incomingLinkToken = new URLSearchParams(location.hash.slice(1)).get("link_token");
        if (incomingLinkToken) {
          sessionStorage.setItem("account_link_token", incomingLinkToken);
          const cleanUrl = new URL(location.href); cleanUrl.hash = "";
          window.history.replaceState({}, "", cleanUrl);
        }
        const config = await api(`/api/auth/line/config?account_id=${encodeURIComponent(accountId)}`);
        await liff.init({ liffId: config.liff_id });
        if (!liff.isLoggedIn()) { liff.login({ redirectUri: location.href }); return; }
        const lineProfile = await liff.getProfile();
        setDisplayName(lineProfile.displayName || "LINE"); setPictureUrl(lineProfile.pictureUrl || "");
        try {
          const csrf = await api(`/api/auth/line/csrf?account_id=${encodeURIComponent(accountId)}`);
          setCsrfToken(csrf.csrf_token);
        } catch {
          const idToken = liff.getIDToken();
          if (!idToken) throw new Error("Missing LINE ID token");
          const challenge = await api("/api/auth/line/challenge", {
            method: "POST",
            body: JSON.stringify({ account_id: accountId, id_token: idToken }),
          });
          const auth = await api("/api/auth/line", {
            method: "POST",
            body: JSON.stringify({ id_token: idToken, account_id: accountId, state: challenge.state }),
          });
          setCsrfToken(auth.csrf_token);
        }
        const linkToken = sessionStorage.getItem("account_link_token");
        if (linkToken) {
          try {
            await api("/api/account-link/complete", {
              method: "POST", body: JSON.stringify({ token: linkToken }),
            });
          } catch {
            setSettingsMessage(t("linkFailed"));
          } finally {
            sessionStorage.removeItem("account_link_token");
          }
        }
        await refresh();
      } catch (reason) { setError(reason.message || String(reason)); }
      finally { setLoading(false); }
    })();
  }, []);

  async function savePreferences() {
    setSavingPreferences(true);
    setPreferenceMessage("");
    try {
      const saved = await api("/api/me/preferences", { method: "PATCH", body: JSON.stringify(preferences) });
      setPreferences(saved);
      setPreferenceMessage(t("preferencesSaved"));
      return true;
    } catch {
      setPreferenceMessage(t("actionFailed"));
      return false;
    } finally {
      setSavingPreferences(false);
    }
  }

  function toggleInterest(value) {
    const selected = preferences.interests.includes(value);
    setPreferences({
      ...preferences,
      interests: selected ? preferences.interests.filter((item) => item !== value) : [...preferences.interests, value].slice(0, 10),
    });
  }

  async function logout() {
    setSettingsMessage("");
    try {
      await api("/api/auth/line/logout", { method: "POST" });
      if (liff.isLoggedIn()) liff.logout();
      location.reload();
    } catch {
      setSettingsMessage(t("actionFailed"));
    }
  }

  async function addFavorite() {
    const title = favoriteInput.trim(); if (!title) return;
    await api("/api/me/favorites", { method: "POST", body: JSON.stringify({ place_id: title, title }) });
    setFavoriteInput(""); setFavorites(await api("/api/me/favorites"));
  }

  async function removeFavorite(item) {
    const previous = favorites;
    setActionError("");
    setRemovingFavorite(item.place_id);
    setFavorites((rows) => rows.filter((row) => row.place_id !== item.place_id));
    try {
      await api(`/api/me/favorites/${encodeURIComponent(item.place_id)}`, { method: "DELETE" });
    } catch {
      setFavorites(previous);
      setActionError(t("actionFailed"));
    } finally {
      setRemovingFavorite("");
    }
  }

  if (loading) return <main className="loading-shell" aria-busy="true" aria-label={translate("zh-TW", "loadingProfile")}><div className="loading-sidebar" /><div className="loading-content"><div className="skeleton title-skeleton" /><div className="skeleton hero-skeleton" /><div className="loading-stats">{[0,1,2,3].map((item)=><div className="skeleton stat-skeleton" key={item} />)}</div></div></main>;
  if (error) return <main className="center error-page"><div><h1>{translate("zh-TW", "loadFailed")}</h1><p>{translate("zh-TW", "loadFailedHint")}</p><button className="primary" onClick={() => location.reload()}>{translate("zh-TW", "retry")}</button></div></main>;

  const tabs = ["home", "favorites", "history", "stories", "preferences"];
  const archiveUrl = import.meta.env.VITE_ARCHIVE_BASE_URL || "https://nfu-digital-archive.zheforge.com/";
  const exploreUrl = `${archiveUrl.replace(/\/+$/, "")}/#collections`;
  const mapUrl = `${archiveUrl.replace(/\/+$/, "")}/#memory-map`;
  const contributionUrl = `${archiveUrl.replace(/\/+$/, "")}/#contribution`;
  const collectionSearchUrl = (query) => `${archiveUrl.replace(/\/+$/, "")}/collections.html?q=${encodeURIComponent(query)}`;
  const selectTab = (name) => { setTab(name); setMenuOpen(false); };
  const puzzleState = puzzle.status === "COMPLETED" ? t("completed") : Object.keys(puzzle).length ? t("inProgress") : "0";

  return <div className="app-shell">
    <button className={`sidebar-backdrop ${menuOpen ? "visible" : ""}`} aria-label={t("closeMenu")} onClick={() => setMenuOpen(false)} />
    <aside className={`sidebar ${menuOpen ? "open" : ""}`} aria-label={t("mainNavigation")}>
      <div className="brand"><span>{t("brandShort")}</span><strong>{t("brandName")}</strong></div>
      <nav className="side-nav">
        <p className="nav-label">{t("title")}</p>
        {tabs.map((name) => <button className={tab === name ? "active" : ""} aria-current={tab === name ? "page" : undefined} onClick={() => selectTab(name)} key={name}><span aria-hidden="true">{t(`${name}Icon`)}</span>{t(name)}</button>)}
      </nav>
      <div className="sidebar-footer">
        <button className={`settings-nav ${tab === "settings" ? "active" : ""}`} aria-current={tab === "settings" ? "page" : undefined} onClick={() => selectTab("settings")}><span aria-hidden="true">{t("settingsIcon")}</span>{t("settings")}</button>
        <a href={archiveUrl}>{t("backToArchive")}</a>
        <p className={`line-status ${linked ? "linked" : ""}`}><span aria-hidden="true" />{linked ? t("lineLinked") : t("lineNotLinked")}</p>
      </div>
    </aside>

    <div className="page">
      <header className="mobile-header">
        <button className="menu-button" aria-label={t("openMenu")} aria-expanded={menuOpen} onClick={() => setMenuOpen(true)}>☰</button>
        <strong>{t("title")}</strong>
        {pictureUrl ? <img src={pictureUrl} alt="" /> : <span className="mini-avatar" aria-hidden="true">H</span>}
      </header>
      <main className="content">
        <header className="content-header"><span className="eyebrow">{t("brandName")}</span><h1>{t("title")}</h1><p>{t("subtitle")}</p></header>
        {tab === "home" && <div className="dashboard">
          <section className="welcome-hero card">
            <div className="welcome-copy">
              <p className="section-kicker">{t("welcome")}</p>
              <h2>{displayName || t("traveler")}</h2>
              <p className="hero-message">{t("heroMessage")}</p>
              <p className="hero-summary">{t("heroSummary", { history: history.length, favorites: favorites.length })}</p>
              <div className="actions"><a className="button primary" href={exploreUrl}>{t("continueExploring")}</a><a className="button" href={archiveUrl}>{t("visitArchive")}</a></div>
            </div>
            {pictureUrl ? <img className="hero-avatar" src={pictureUrl} alt="" /> : <div className="hero-avatar avatar" aria-hidden="true">H</div>}
          </section>

          <section className="stats-grid" aria-label={t("exploreStats")}>
            <button className="stat-card" onClick={() => selectTab("favorites")}><span>{t("favoritesStat")}</span><strong>{favorites.length}</strong><small>{t("favoritesStatHint")}</small></button>
            <button className="stat-card" onClick={() => selectTab("history")}><span>{t("historyStat")}</span><strong>{history.length}</strong><small>{t("historyStatHint")}</small></button>
            <button className="stat-card" onClick={() => selectTab("history")}><span>{t("puzzleStat")}</span><strong className="text-value">{puzzleState}</strong><small>{t("puzzleStatHint")}</small></button>
            <button className="stat-card unavailable" onClick={() => selectTab("stories")}><span>{t("storiesStat")}</span><strong className="text-value">—</strong><small>{t("notAvailableYet")}</small></button>
          </section>

          <div className="dashboard-columns">
            <section className="dashboard-section card">
              <div className="section-heading"><div><p className="section-kicker">{t("personalizedGuide")}</p><h2>{t("recommendedForYou")}</h2><p>{t("recommendationSubtitle")}</p></div></div>
              <div className="empty-state"><span aria-hidden="true">◇</span><h3>{t("recommendationEmpty")}</h3><p>{t("recommendationEmptyHint")}</p><button className="primary" onClick={() => selectTab("preferences")}>{t("setPreferences")}</button></div>
            </section>

            <section className="dashboard-section card">
              <div className="section-heading"><div><p className="section-kicker">{t("yourJourney")}</p><h2>{t("recentExploration")}</h2></div>{history.length > 0 && <button className="text-button" onClick={() => selectTab("history")}>{t("viewAll")}</button>}</div>
              {history.length ? <ul className="recent-list">{history.slice(0, 3).map((item) => <li key={item.id}><div><strong>{item.query || item.full_itinerary?.title || t("exploration")}</strong><p>{item.status || t("historyRecord")}</p></div><time>{formatDate(item.created_at, preferences.language)}</time></li>)}</ul> : <div className="empty-state compact"><span aria-hidden="true">◎</span><h3>{t("historyEmpty")}</h3><p>{t("historyEmptyHint")}</p><a className="button" href={exploreUrl}>{t("startExploring")}</a></div>}
            </section>
          </div>

        </div>}
        {tab === "preferences" && <div className="preferences-page">
          <section className="page-intro"><div><p className="section-kicker">{t("personalizedGuide")}</p><h2>{t("preferences")}</h2><p>{t("preferencesIntro")}</p></div></section>
          <section className="preference-section card"><div className="preference-heading"><span>01</span><div><h3>{t("preferenceQuestion")}</h3><p>{t("preferenceQuestionHint")}</p></div></div><div className="chip-group" aria-label={t("interests")}>{interestOptions.map((value) => <button className={preferences.interests.includes(value) ? "selected" : ""} aria-pressed={preferences.interests.includes(value)} onClick={() => toggleInterest(value)} key={value}>{t(`interest_${value}`)}</button>)}</div></section>
          <section className="preference-section card"><div className="preference-heading"><span>02</span><div><h3>{t("contentDepthQuestion")}</h3><p>{t("contentDepthHint")}</p></div></div><div className="select-card-grid">{depthOptions.map((value) => <button className={preferences.content_depth === value ? "selected" : ""} aria-pressed={preferences.content_depth === value} onClick={() => setPreferences({...preferences, content_depth:value})} key={value}><strong>{t(`depth_${value}`)}</strong><small>{t(`depth_${value}_hint`)}</small></button>)}</div></section>
          <section className="preference-section card"><div className="preference-heading"><span>03</span><div><h3>{t("durationQuestion")}</h3><p>{t("durationHint")}</p></div></div><div className="duration-grid">{durationOptions.map((value) => <button className={preferences.preferred_duration === value ? "selected" : ""} aria-pressed={preferences.preferred_duration === value} onClick={() => setPreferences({...preferences, preferred_duration:value})} key={value}>{t(`duration_${value}`)}</button>)}</div></section>
          <aside className="bot-personalization"><span aria-hidden="true">◇</span><div><strong>{t("botPersonalizationTitle")}</strong><p>{t("botPersonalizationHint")}</p></div></aside>
          <details className="advanced-preferences card"><summary>{t("advancedPreferences")}</summary><div className="form advanced-form">
            <label>{t("language")}<select value={preferences.language} onChange={(e) => setPreferences({...preferences, language:e.target.value})}><option value="zh-TW">繁體中文</option><option value="en-US">English</option><option value="ja-JP">日本語</option></select></label>
            <label>{t("transportation")}<select value={preferences.transportation} onChange={(e) => setPreferences({...preferences, transportation:e.target.value})}>{["walking","bicycle","transit","driving"].map(v=><option value={v} key={v}>{t(v)}</option>)}</select></label>
            <label>{t("walkingPreference")}<select value={preferences.walking_preference} onChange={(e) => setPreferences({...preferences, walking_preference:e.target.value})}>{["low","medium","high"].map(v=><option value={v} key={v}>{t(v)}</option>)}</select></label>
            <label>{t("stay")}<input type="number" min="15" max="480" value={preferences.stay_minutes} onChange={(e) => setPreferences({...preferences, stay_minutes:Number(e.target.value)})} /></label>
            <fieldset><legend>{t("voice")}</legend><input aria-label="speaker" value={preferences.voice.speaker} onChange={(e)=>setPreferences({...preferences,voice:{...preferences.voice,speaker:e.target.value}})} /><input aria-label="speed" type="number" min="0.5" max="2" step="0.1" value={preferences.voice.speed} onChange={(e)=>setPreferences({...preferences,voice:{...preferences.voice,speed:Number(e.target.value)}})} /><input aria-label="pitch" type="number" min="-12" max="12" step="1" value={preferences.voice.pitch} onChange={(e)=>setPreferences({...preferences,voice:{...preferences.voice,pitch:Number(e.target.value)}})} /></fieldset>
          </div></details>
          {preferenceMessage && <p className="save-message" role="status">{preferenceMessage}</p>}
          <div className="preference-actions"><button className="primary" disabled={savingPreferences} onClick={savePreferences}>{savingPreferences ? t("saving") : t("savePreferences")}</button><button onClick={async()=>{await api("/api/me/preferences",{method:"DELETE"});await refresh();setPreferenceMessage(t("preferencesReset"));}}>{t("resetPreferences")}</button></div>
        </div>}
        {tab === "favorites" && <div className="collection-page">
          <section className="page-intro"><div><p className="section-kicker">{t("savedMemories")}</p><h2>{t("favorites")}</h2><p>{t("favoritesIntro")}</p></div><span className="count-badge">{t("itemsCount", { count: favorites.length })}</span></section>
          {actionError && <p className="inline-error" role="alert">{actionError}</p>}
          {favorites.length ? <div className="favorite-grid">{favorites.map((item) => {
            const title = item.title || item.place_id;
            const isRemoving = removingFavorite === item.place_id;
            return <article className={`favorite-card ${isRemoving ? "removing" : ""}`} key={item.id || item.place_id}>
              <div className="favorite-visual" aria-hidden="true">故</div>
              <div className="favorite-body"><p className="content-type">{t("placeMemory")}</p><h3>{title}</h3><p className="saved-date">{t("savedOn", { date: formatDate(item.created_at, preferences.language) || t("unknownDate") })}</p><div className="card-actions"><a className="text-link" href={collectionSearchUrl(title)}>{t("viewContent")}</a><button disabled={isRemoving} onClick={() => removeFavorite(item)}>{isRemoving ? t("removing") : t("removeFavorite")}</button></div></div>
            </article>;
          })}</div> : <div className="empty-state page-empty"><span aria-hidden="true">♡</span><h3>{t("favoritesEmpty")}</h3><p>{t("favoritesEmptyHint")}</p><a className="button primary" href={exploreUrl}>{t("exploreCollections")}</a></div>}
          <details className="legacy-add"><summary>{t("manualFavorite")}</summary><div className="inline"><input value={favoriteInput} onChange={(e)=>setFavoriteInput(e.target.value)} placeholder={t("addFavorite")} /><button className="primary" onClick={addFavorite}>＋</button></div></details>
        </div>}
        {tab === "history" && <div className="footprint-page">
          <section className="page-intro"><div><p className="section-kicker">{t("yourJourney")}</p><h2>{t("history")}</h2><p>{t("footprintSummary", { count: history.length })}</p></div><a className="button" href={mapUrl}>{t("viewOnMap")}</a></section>
          <div className="exploration-panels">
            <section className="memory-exploration card">
              <div className="panel-heading"><div><p className="section-kicker">{t("culturalQuest")}</p><h3>{t("puzzles")}</h3></div><span className={`status-badge ${puzzle.status === "COMPLETED" ? "complete" : ""}`}>{puzzleState === "0" ? t("notStarted") : puzzleState}</span></div>
              {Object.keys(puzzle).length ? <div className="quest-state"><p>{t("currentQuest")}</p><strong>{puzzle.current_stage || t("questCompleted")}</strong><small>{puzzle.status === "COMPLETED" ? t("questCompletedHint") : t("continueInLine")}</small><button onClick={async()=>{if(window.confirm(t("confirmClearPuzzle"))){await api("/api/me/puzzles",{method:"DELETE"});setPuzzle({});}}}>{t("clearPuzzle")}</button></div> : <div className="empty-state compact"><span aria-hidden="true">◇</span><h3>{t("puzzleEmpty")}</h3><p>{linked ? t("startPuzzleInLine") : t("linkForPuzzle")}</p></div>}
            </section>
            <section className="memory-badges card">
              <div className="panel-heading"><div><p className="section-kicker">{t("localAchievements")}</p><h3>{t("memoryBadges")}</h3></div></div>
              <div className="empty-state compact"><span aria-hidden="true">✦</span><h3>{t("badgesEmpty")}</h3><p>{t("badgesEmptyHint")}</p></div>
            </section>
          </div>
          {history.length ? <ol className="footprint-timeline">{history.map((item) => {
            const itinerary = item.full_itinerary && typeof item.full_itinerary === "object" ? item.full_itinerary : {};
            const title = itinerary.title || item.query || t("exploration");
            const stopCount = Array.isArray(itinerary.stops) ? itinerary.stops.length : 0;
            return <li key={item.id}><span className="timeline-marker" aria-hidden="true" /><article><div className="timeline-meta"><span>{t("placeExploration")}</span><time>{formatDate(item.created_at, preferences.language)}</time></div><h3>{title}</h3><p>{stopCount ? t("stopsCount", { count: stopCount }) : historyStatus(item.status, t)}</p></article></li>;
          })}</ol> : <div className="empty-state page-empty"><span aria-hidden="true">◎</span><h3>{t("historyEmpty")}</h3><p>{t("historyEmptyHint")}</p><a className="button primary" href={exploreUrl}>{t("startExploring")}</a></div>}
          {history.length > 0 && <details className="history-tools"><summary>{t("historyManagement")}</summary><button onClick={async()=>{if(window.confirm(t("confirmClearHistory"))){await api("/api/me/history",{method:"DELETE"});setHistory([]);}}}>{t("clearHistory")}</button></details>}
        </div>}
        {tab === "stories" && <div className="stories-page">
          <section className="page-intro"><div><p className="section-kicker">{t("communityMemory")}</p><h2>{t("stories")}</h2><p>{t("storiesIntro")}</p></div></section>
          <div className="empty-state page-empty stories-empty"><span aria-hidden="true">▧</span><h3>{t("storiesEmpty")}</h3><p>{t("storiesEmptyHint")}</p><a className="button primary" href={contributionUrl}>{t("shareHuweiStory")}</a></div>
        </div>}
        {tab === "settings" && <div className="settings-page">
          <section className="page-intro"><div><p className="section-kicker">{t("accountAndPrivacy")}</p><h2>{t("settings")}</h2><p>{t("settingsIntro")}</p></div></section>
          {settingsMessage && <p className="save-message" role="status">{settingsMessage}</p>}
          <section className="settings-card card"><div className="settings-heading"><div className="profile-identity">{pictureUrl ? <img src={pictureUrl} alt="" /> : <span className="avatar" aria-hidden="true">H</span>}<div><p>{t("personalProfile")}</p><h3>{displayName || t("traveler")}</h3><small>{t("profileFromLine")}</small></div></div></div></section>
          <section className="settings-card card"><div className="settings-heading"><div><p className="section-kicker">LINE</p><h3>{t("lineAccount")}</h3><p>{linked ? t("lineLinkedHint") : t("lineNotLinkedHint")}</p></div><span className={`account-status ${linked ? "linked" : ""}`}><i aria-hidden="true" />{linked ? t("lineLinked") : t("lineNotLinked")}</span></div>{linked ? <button onClick={async()=>{if(window.confirm(t("confirmUnlink"))){await api("/api/account-link",{method:"DELETE"});setLinked(false);setSettingsMessage(t("unlinkedMessage"));}}}>{t("unlink")}</button> : <div className="binding-help"><strong>{t("howToLink")}</strong><p>{t("linkInstruction")}</p></div>}</section>
          <section className="settings-card card"><div className="settings-heading"><div><p className="section-kicker">{t("interface")}</p><h3>{t("language")}</h3><p>{t("languageHint")}</p></div></div><div className="setting-control"><select aria-label={t("language")} value={preferences.language} onChange={(e) => setPreferences({...preferences, language:e.target.value})}><option value="zh-TW">繁體中文</option><option value="en-US">English</option><option value="ja-JP">日本語</option></select><button className="primary" disabled={savingPreferences} onClick={async()=>{if(await savePreferences())setSettingsMessage(t("languageSaved"));}}>{t("saveLanguage")}</button></div></section>
          <section className="settings-card card"><div className="settings-heading"><div><p className="section-kicker">{t("privacy")}</p><h3>{t("personalData")}</h3><p>{t("privacyHint")}</p></div></div><div className="privacy-actions"><button onClick={async()=>{if(window.confirm(t("confirmClearPreferences"))){await api("/api/me/preferences",{method:"DELETE"});await refresh();setSettingsMessage(t("preferencesCleared"));}}}>{t("clearPreferences")}</button><button onClick={async()=>{if(window.confirm(t("confirmClearHistory"))){await api("/api/me/history",{method:"DELETE"});setHistory([]);setSettingsMessage(t("historyCleared"));}}}>{t("clearHistory")}</button><button className="danger" onClick={async()=>{if(window.confirm(t("confirmClearAll"))){await api("/api/me",{method:"DELETE"});await refresh();setSettingsMessage(t("personalDataCleared"));}}}>{t("clearAll")}</button></div></section>
          <section className="settings-card card logout-card"><div><h3>{t("logout")}</h3><p>{t("logoutHint")}</p></div><button onClick={logout}>{t("logout")}</button></section>
        </div>}
      </main>
      <nav className="bottom-nav" aria-label={t("quickNavigation")}>
        {["home", "favorites", "history", "settings"].map((name) => <button className={tab === name ? "active" : ""} aria-current={tab === name ? "page" : undefined} onClick={() => selectTab(name)} key={name}><span aria-hidden="true">{t(`${name}Icon`)}</span>{t(`mobile_${name}`)}</button>)}
      </nav>
    </div>
  </div>;
}

function List({ rows, empty, render }) { return rows.length ? <ul>{rows.map((row, index)=><li key={row.id || index}>{render(row)}</li>)}</ul> : <p className="muted">{empty}</p>; }

function formatDate(value, language) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : new Intl.DateTimeFormat(language, { month: "short", day: "numeric" }).format(date);
}

function historyStatus(status, t) {
  if (status === "RATED") return t("ratedJourney");
  if (status === "READY") return t("readyJourney");
  return t("historyRecord");
}

createRoot(document.getElementById("root")).render(<App />);
