"""Explicit public selections and trusted read-only local static-project catalog."""
import os,re,unicodedata
from pathlib import Path
from urllib.parse import urlsplit,parse_qsl,unquote
from pydantic import BaseModel,ConfigDict,Field

class Selection(BaseModel):
    model_config=ConfigDict(extra='forbid')
    public_urls:list[str]=Field(default_factory=list,max_length=4)
    project_ids:list[str]=Field(default_factory=list,max_length=4)

class Project(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    id:str
    label:str
    root:str
    public_dir:str

class Catalog(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    projects:list[Project]

PUBLIC_QUERY_KEYS={'q','query','search','lang','hl','page','p','limit','offset','sort','order','view','tab','url'}

def public_url(value,depth=0):
    # Nested link values get credential checks, not permission to fetch that link.
    u=urlsplit(value)
    invalid=(depth>4 or len(value)>2000 or not u.hostname or u.username or u.password
             or '#' in value or u.scheme not in (('https',) if depth==0 else ('http','https'))
             or (depth==0 and u.port not in (None,443)))
    if invalid:raise ValueError('Select a public HTTPS URL without credentials, fragments or custom ports')
    for key,val in parse_qsl(u.query,keep_blank_values=True,errors='strict'):
        if key.lower() not in PUBLIC_QUERY_KEYS:raise ValueError('Unsupported URL query; select a public link without credential or unknown parameters')
        candidate=val
        for _ in range(4):
            decoded=unquote(candidate,errors='strict')
            # Reject ambiguous boundary chars before Python/JS trim can disagree.
            if any(unicodedata.category(c).startswith('C') or c=='\ufffd' for c in decoded):raise ValueError('Ambiguous Unicode URL query characters')
            decoded=decoded.strip()
            if decoded==candidate:break
            candidate=decoded
        if '%' in candidate or '\\' in candidate or ';' in candidate or re.search(r'[\x00-\x1f\x7f]',candidate):raise ValueError('Ambiguous URL query encoding, separator or control characters')
        if candidate.startswith('//'):raise ValueError('Ambiguous nested URL; use a public absolute or root-relative link')
        absolute=bool(re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:',candidate))
        if key.lower()=='url':
            if val!=candidate or re.search(r'\s',candidate) or not (absolute or candidate.startswith('/')):raise ValueError('Ambiguous nested URL; use a canonical public link')
        if absolute:public_url(candidate,depth+1)
        else:public_url('https://relative.invalid/'+candidate.lstrip('/'),depth+1)
    return u

def catalog():
    filename=os.environ.get('SELF_PODCAST_SOURCE_CATALOG')
    if not filename:return []
    p=Path(filename)
    if p.is_symlink() or p.stat().st_uid!=os.getuid() or p.stat().st_mode&0o022:raise ValueError('Source catalog must be owned by you and not group/world writable')
    projects=Catalog.model_validate_json(p.read_text()).projects;result=[];seen=set()
    for item in projects:
        ident=item.id
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,50}',ident) or ident in seen:raise ValueError('Invalid/duplicate trusted project ID')
        seen.add(ident);root=Path(item.root).resolve(strict=True);directory=(root/item.public_dir).resolve(strict=True)
        if not directory.is_dir() or directory==root or not directory.is_relative_to(root):raise ValueError('Choose a public subdirectory inside the existing project')
        result.append({'id':ident,'label':item.label[:180],'root':str(directory)})
    return result

def selected_sources(selection):
    selected=Selection.model_validate(selection);result=[]
    try:projects={p['id']:p for p in catalog()} if selected.project_ids else {}
    except (OSError,KeyError,ValueError) as e:raise ValueError('Trusted local source catalog unavailable or invalid; review host configuration') from e
    if len(selected.public_urls)+len(selected.project_ids)>4:raise ValueError('Select at most four visual sources')
    for url in selected.public_urls:
        u=public_url(url)
        result.append({'id':'s'+str(len(result)),'type':'public','url':url,'label':u.hostname})
    for ident in selected.project_ids:
        if ident not in projects:raise ValueError('Unknown local project; select an ID from the trusted source catalog')
        p=projects[ident];result.append({'id':'s'+str(len(result)),'type':'local','project_id':ident,'label':p['label'],'root':p['root'],'path':'/'})
    return result
