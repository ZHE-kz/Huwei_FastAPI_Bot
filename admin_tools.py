import hmac
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

from config import ADMIN_TOKEN
from firestore_client import get_db
from puzzle_core import PUZZLE_COLLECTION, force_clear_puzzle_cache, load_puzzle_config, normalize_stage

router = APIRouter(prefix="/admin/puzzles")
security = HTTPBasic(auto_error=False)


def require_admin(credentials: HTTPBasicCredentials = Depends(security)):
    valid = (
        credentials
        and hmac.compare_digest(credentials.username, "admin")
        and hmac.compare_digest(credentials.password, ADMIN_TOKEN)
    )
    if not ADMIN_TOKEN:
        raise HTTPException(503, "ADMIN_TOKEN 尚未設定")
    if not valid:
        raise HTTPException(401, "Unauthorized", headers={"WWW-Authenticate": "Basic"})


class PuzzleSettings(BaseModel):
    start_command: str
    start_stage: str


class PuzzleStage(BaseModel):
    agent_intro: str
    vision_target: str = ""
    puzzle_hint: str
    puzzle_answer: str
    success_text: str
    next_stage_id: str = ""
    requires_image: bool = False


@router.get("", response_class=HTMLResponse, dependencies=[Depends(require_admin)])
async def puzzle_admin_page():
    return HTMLResponse(ADMIN_HTML)


@router.get("/api", dependencies=[Depends(require_admin)])
async def list_puzzles():
    return await load_puzzle_config()


@router.put("/api/settings", dependencies=[Depends(require_admin)])
async def update_settings(settings: PuzzleSettings):
    if not settings.start_command.strip() or not settings.start_stage.strip():
        raise HTTPException(400, "啟動指令與起始關卡不可空白")
    get_db().collection(PUZZLE_COLLECTION).document("_settings").set(settings.model_dump())
    force_clear_puzzle_cache()
    return {"ok": True}


@router.put("/api/stages/{stage_id}", dependencies=[Depends(require_admin)])
async def update_stage(stage_id: str, stage: PuzzleStage):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,50}", stage_id):
        raise HTTPException(400, "關卡 ID 只能使用英數、底線與連字號")
    data = normalize_stage(stage_id, stage.model_dump())
    get_db().collection(PUZZLE_COLLECTION).document(stage_id).set(data)
    force_clear_puzzle_cache()
    return {"ok": True, "stage": data}


ADMIN_HTML = """<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>解謎題庫管理</title><style>
body{font:16px system-ui;max-width:980px;margin:auto;padding:24px;background:#f5f7f5;color:#18311f}h1{margin-top:0}
section{background:white;padding:20px;margin:16px 0;border-radius:12px;box-shadow:0 2px 12px #0001}label{display:block;margin:10px 0 4px}
input,textarea{box-sizing:border-box;width:100%;padding:10px;border:1px solid #b8c7bb;border-radius:7px}textarea{min-height:76px}button{margin-top:14px;padding:10px 16px;border:0;border-radius:7px;background:#1d7a3b;color:white;cursor:pointer}.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.stage{border-top:1px solid #ddd;padding:12px 0}.muted{color:#607067}@media(max-width:650px){.grid{grid-template-columns:1fr}}
</style></head><body><h1>解謎題庫管理</h1><p class="muted">使用者輸入啟動指令後，從起始關卡開始。修改會直接寫入 Firestore。</p>
<section><h2>遊戲設定</h2><form id="settings"><div class="grid"><div><label>啟動指令</label><input name="start_command" required></div><div><label>起始關卡</label><input name="start_stage" required></div></div><button>儲存設定</button></form></section>
<section><h2>新增／修改關卡</h2><form id="stage"><div class="grid"><div><label>關卡 ID</label><input name="stage_id" placeholder="STAGE_01" required></div><div><label>下一關 ID</label><input name="next_stage_id"></div></div><label>開場文字</label><textarea name="agent_intro" required></textarea><label>圖片辨識目標</label><textarea name="vision_target"></textarea><label><input style="width:auto" type="checkbox" name="requires_image"> 此關需要先上傳照片</label><label>題目／提示</label><textarea name="puzzle_hint" required></textarea><label>正確答案</label><input name="puzzle_answer" required><label>答對訊息</label><textarea name="success_text" required></textarea><button>儲存關卡</button></form></section>
<section><h2>目前關卡</h2><div id="list"></div></section><script>
const settings=document.querySelector('#settings'),stage=document.querySelector('#stage'),list=document.querySelector('#list');
async function api(path='',options={}){const r=await fetch('/admin/puzzles/api'+path,{headers:{'Content-Type':'application/json'},...options});if(!r.ok)throw new Error(await r.text());return r.json()}
async function load(){const data=await api();settings.start_command.value=data.settings.start_command;settings.start_stage.value=data.settings.start_stage;list.replaceChildren(...Object.entries(data.stages).sort().map(([id,s])=>{const row=document.createElement('div');row.className='stage';const title=document.createElement('strong');title.textContent=id+' — '+s.puzzle_hint;const edit=document.createElement('button');edit.textContent='編輯';edit.onclick=()=>fill(id,s);row.append(title,document.createElement('br'),edit);return row}))}
function fill(id,s){stage.stage_id.value=id;for(const [key,value] of Object.entries(s)){if(stage[key])stage[key].type==='checkbox'?stage[key].checked=value:stage[key].value=value??''}stage.scrollIntoView({behavior:'smooth'})}
settings.onsubmit=async e=>{e.preventDefault();await api('/settings',{method:'PUT',body:JSON.stringify(Object.fromEntries(new FormData(settings)))});alert('設定已儲存')};
stage.onsubmit=async e=>{e.preventDefault();const data=Object.fromEntries(new FormData(stage));const id=data.stage_id;delete data.stage_id;data.requires_image=stage.requires_image.checked;await api('/stages/'+encodeURIComponent(id),{method:'PUT',body:JSON.stringify(data)});alert('關卡已儲存');await load()};load();
</script></body></html>"""