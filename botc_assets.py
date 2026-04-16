import re,os,json,urllib.request,urllib.error
ASSET_DIR='/home/discord-bot/assets'
TOKEN_DIR=ASSET_DIR+'/tokens'
MANIFEST_PATH=ASSET_DIR+'/manifest.json'
CDN='https://clocktower.live/img/'
_mc=None
def _appjs():
    with urllib.request.urlopen('https://clocktower.live/') as r:
        h=r.read().decode()
    m=re.search(r'src="(/js/app\.[a-f0-9]+\.js)"',h)
    return 'https://clocktower.live'+m.group(1)
def build_manifest(save=True):
    with urllib.request.urlopen(_appjs()) as r:
        t=r.read().decode()
    imgs=set(re.findall(r'[a-zA-Z0-9_\-]+\.[a-f0-9]{8}\.webp',t))
    roles={}
    for f in imgs:
        m=re.match(r'^([a-z0-9]+)_([ge])\.',f)
        p=re.match(r'^([a-z0-9]+)\.[a-f0-9]',f)
        if m: roles.setdefault(m.group(1),{})[('good'if m.group(2)=='g'else'evil')]=f
        elif p: roles.setdefault(p.group(1),{})['reminder']=f
    def _f(k): return next((f for f in imgs if re.match(rf'^{k}\.[a-f0-9]+\.webp$',f)),None)
    base={k:_f(k) for k in('token','reminder','death','shroud','vote','tb','bmr','snv','custom')}
    mf={'base':base,'roles':roles}
    if save:
        os.makedirs(ASSET_DIR,exist_ok=True)
        json.dump(mf,open(MANIFEST_PATH,'w'))
    return mf
def get_manifest():
    global _mc
    if _mc: return _mc
    if os.path.exists(MANIFEST_PATH):
        _mc=json.load(open(MANIFEST_PATH))
    else: _mc=build_manifest()
    return _mc
def download_all(mf=None,verbose=True):
    if mf is None: mf=get_manifest()
    os.makedirs(TOKEN_DIR,exist_ok=True)
    files=list(set([v for v in mf['base'].values() if v]+[v for rd in mf['roles'].values() for v in rd.values() if v]))
    n=0
    for fn in files:
        dest=TOKEN_DIR+'/'+fn
        if os.path.exists(dest): continue
        try:
            urllib.request.urlretrieve(CDN+fn,dest); n+=1
            if verbose: print(f' {fn}')
        except: pass
    return n
def get_base_path(key):
    mf=get_manifest(); fn=mf['base'].get(key)
    if not fn: return None
    p=TOKEN_DIR+'/'+fn
    if not os.path.exists(p):
        try: urllib.request.urlretrieve(CDN+fn,p)
        except: return None
    return p
def _key(s): return __import__('re').sub(r'[^a-z0-9]','',s.lower())
def get_token_path(role_id,use_evil=False):
    mf=get_manifest(); e=mf['roles'].get(_key(role_id))
    if not e: return None
    fn=e.get('evil'if use_evil else'good')or e.get('good')or e.get('evil')
    if not fn: return None
    p=TOKEN_DIR+'/'+fn
    if not os.path.exists(p):
        try: urllib.request.urlretrieve(CDN+fn,p)
        except: return None
    return p
def get_reminder_path(role_id):
    mf=get_manifest(); e=mf['roles'].get(_key(role_id))
    if not e: return None
    fn=e.get('reminder')
    if not fn: return None
    p=TOKEN_DIR+'/'+fn
    if not os.path.exists(p):
        try: urllib.request.urlretrieve(CDN+fn,p)
        except: return None
    return p

if __name__=='__main__':
    print('Building manifest...')
    mf=build_manifest()
    print('Downloading...')
    n=download_all(mf)
    print(f'Done — {n} new files')
