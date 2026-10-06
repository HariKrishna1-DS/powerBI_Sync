const {test} = require('node:test');
const assert = require('node:assert/strict');
const {createCloudAuth, validateCloudConfig, PROJECT} = require('../cloud-auth.cjs');
const {publicSettings, DEFAULTS} = require('../settings.cjs');
const user = {id:'00000000-0000-0000-0000-000000000001',email:'qa@example.test'};
const config = {url:PROJECT,publishableKey:'sb_publishable_fixtureonly123'};
const session = (suffix='one') => ({access_token:`header.payload.${suffix}`,refresh_token:`refresh-${suffix}`,expires_in:3600,user});
const response = (body, status=200) => ({ok:status>=200&&status<300,status,json:async()=>body});
function setup(fetcher, initial={}) {
  let settings={...DEFAULTS,cloudConfig:config,...initial};
  const saved=[];
  const auth=createCloudAuth({read:()=>settings,write:value=>{settings=value;saved.push(value);},fetcher,now:()=>1000000});
  return {auth,read:()=>settings,saved};
}

test('configuration rejects privileged keys, HTTP, credentials and foreign hosts',()=>{
  for(const input of [{...config,publishableKey:'sb_secret_fixtureonly123'}, {...config,url:PROJECT+'.evil.test'},
    {...config,url:PROJECT.replace('https:','http:')}, {...config,url:PROJECT+'/redirect'}]) assert.throws(()=>validateCloudConfig(input));
  assert.deepEqual(validateCloudConfig(config),config);
});

test('sign-in persists only session credentials; public responses never expose tokens or password',async()=>{
  let request;
  const {auth,read}=setup(async(url,options)=>{request={url,options};return response(session());});
  const result=await auth.signIn({email:user.email,password:'fixture-only-password'});
  assert.equal(result.signedIn,true);
  assert.equal(request.options.redirect,'error');
  assert.equal(request.url,PROJECT+'/auth/v1/token?grant_type=password');
  assert.equal(JSON.stringify(read()).includes('fixture-only-password'),false);
  assert.equal(JSON.stringify(result).includes('refresh-one'),false);
  const publicValue=JSON.stringify(publicSettings(read()));
  assert.equal(publicValue.includes('refresh-one'),false);
  assert.equal(publicValue.includes('header.payload.one'),false);
  assert.equal(read().cloudSession.refresh_token,'refresh-one');
});

test('simultaneous refreshes are serialized and rotate the token exactly once',async()=>{
  let calls=0;
  const {auth,read}=setup(async()=>{calls++;await new Promise(resolve=>setTimeout(resolve,5));return response(session('two'));},
    {cloudSession:{...session(),expires_at:900}});
  const values=await Promise.all([auth.accessToken(),auth.accessToken(),auth.accessToken(),auth.accessToken()]);
  assert.deepEqual(values,Array(4).fill('header.payload.two'));
  assert.equal(calls,1);
  assert.equal(read().cloudSession.refresh_token,'refresh-two');
});

test('failed encrypted persistence cannot report a successful sign-in',async()=>{
  const auth=createCloudAuth({read:()=>({cloudConfig:config}),write:()=>{throw Error('Encryption failed');},fetcher:async()=>response(session())});
  await assert.rejects(auth.signIn({email:user.email,password:'fixture'}),/Encryption failed/);
  assert.equal(auth.status().signedIn,false);
});

test('sign-out revokes this device only and still clears locally during outages',async()=>{
  for(const offline of [false,true]) {
    let requested;
    const {auth,read}=setup(async url=>{requested=url;if(offline)throw Error('private upstream detail');return response(null,204);},
      {cloudSession:{...session(),expires_at:5000}});
    const result=await auth.signOut();
    assert.equal(requested,PROJECT+'/auth/v1/logout?scope=local');
    assert.equal(result.remoteRevoked,!offline);
    assert.equal(read().cloudSession,null);
  }
});

test('expired refresh tokens require sign-in and network failures preserve recovery state',async()=>{
  for(const status of [401,503]) {
    const {auth,read}=setup(async()=>response({message:'do not reveal'},status),{cloudSession:{...session(),expires_at:900}});
    await assert.rejects(auth.accessToken(),error=>!error.message.includes('do not reveal'));
    assert.equal(!!read().cloudSession,status===503);
  }
});

test('invalid session responses never persist and sign-out waits for in-flight sign-in',async()=>{
  const invalid=setup(async()=>response({...session(),refresh_token:''}));
  await assert.rejects(invalid.auth.signIn({email:user.email,password:'fixture'}),/could not be verified/);
  assert.equal(invalid.saved.length,0);
  const {auth,read}=setup(async url=>url.includes('/token?')?response(session()):response(null,204));
  await Promise.all([auth.signIn({email:user.email,password:'fixture'}),auth.signOut()]);
  assert.equal(read().cloudSession,null);
});

test('workspace creation retries the persisted identifier after an ambiguous response',async()=>{
  const submitted=[];
  const {auth,read}=setup(async(url,options)=>{
    if(url.endsWith('tv_list_workspaces'))return response([]);
    const body=JSON.parse(options.body);submitted.push(body);
    if(submitted.length===1)throw Error('Connection lost after commit');
    return response(body.p_workspace);
  },{cloudSession:{...session(),expires_at:5000}});
  const input={name:'Tv Tracker',queueScope:'queue-23656'};
  await assert.rejects(auth.createWorkspace(input),/unreachable/);
  const id=read().cloudWorkspaceDraft.id;
  assert.deepEqual(await auth.createWorkspace(input),{id,existing:false});
  assert.equal(submitted.length,2);
  assert.equal(submitted[0].p_workspace,submitted[1].p_workspace);
});

test('an existing permitted workspace is reused instead of creating another',async()=>{
  let calls=0;
  const {auth}=setup(async()=>{calls++;return response([{id:user.id,name:'Tv Tracker',queue_scope:'queue-23656',role:'owner',mode:'shadow'}]);},
    {cloudSession:{...session(),expires_at:5000}});
  assert.deepEqual(await auth.createWorkspace({name:'Tv Tracker',queueScope:'queue-23656'}),{id:user.id,existing:true});
  assert.equal(calls,1);
});

test('invalid membership cannot create a duplicate or return an unverified workspace',async()=>{
  let calls=0;
  const {auth}=setup(async()=>{calls++;return response([{id:'invalid',queue_scope:'queue-23656'}]);},
    {cloudSession:{...session(),expires_at:5000}});
  await assert.rejects(auth.createWorkspace({name:'Tv Tracker',queueScope:'queue-23656'}),/membership/);
  assert.equal(calls,1);
});

test('joining requires active server membership and the exact designated worker',async()=>{
  const id=user.id, worker='00000000-0000-0000-0000-000000000099';
  const member={id,name:'Tv Tracker',queue_scope:'queue-23656',role:'editor',mode:'active'};
  const detail={id,mode:'active',queue_scope:member.queue_scope,worker,spreadsheet:'synthetic_workbook_12345678'};
  const {auth,read}=setup(async url=>response(url.endsWith('tv_list_workspaces')?[member]:detail),
    {cloudSession:{...session(),expires_at:5000},queueUrl:member.queue_scope});
  await assert.rejects(auth.joinWorkspace({id,officeWorker:true}),/designated/);
  assert.equal(read().cloudWorkspace,undefined);
  const selected=await auth.joinWorkspace({id,officeWorker:false});
  assert.equal(selected.userId,user.id);
  assert.equal(selected.officeWorker,false);
  member.mode='shadow';
  await assert.rejects(auth.joinWorkspace({id,officeWorker:false}),/activation/);
});

test('office worker identity survives retries and wrong-account sign-in cannot replace the workspace session',async()=>{
  const {auth,read}=setup(async()=>response({...session(),user:{...user,id:'00000000-0000-0000-0000-000000000002'}}),
    {cloudWorkspace:{userId:user.id}});
  const worker=await auth.workerIdentity();
  assert.equal(await auth.workerIdentity(),worker);
  await assert.rejects(auth.signIn({email:user.email,password:'fixture'}),/another account/);
  assert.equal(read().cloudSession,undefined);
});
