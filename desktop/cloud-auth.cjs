// Supabase credentials stay in the main process and the encrypted Windows vault.
// Never expose access/refresh tokens through preload or renderer responses.
const PROJECT = 'https://qontoybecrqpbjzoajqf.supabase.co';
const {randomUUID} = require('node:crypto');
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function validateCloudConfig(input) {
  if (!input || typeof input !== 'object' ||
      typeof input.url !== 'string' || !/^https:\/\/[a-z0-9]{20}\.supabase\.co$/.test(input.url) ||
      typeof input.publishableKey !== 'string' || !/^sb_publishable_[A-Za-z0-9_-]{10,256}$/.test(input.publishableKey)) {
    throw Error('Use the Supabase project URL and its publishable key. Administrator keys are not allowed on client PCs.');
  }
  return {url: input.url, publishableKey: input.publishableKey};
}

function verifiedWorkspaces(rows) {
  if (!Array.isArray(rows) || rows.some(row => !row || !UUID.test(row.id || '') || typeof row.name !== 'string' ||
      typeof row.queue_scope !== 'string' || !row.queue_scope ||
      !['owner','editor','viewer'].includes(row.role) || !['shadow','active'].includes(row.mode))) {
    throw Error('Workspace membership could not be verified.');
  }
  return rows;
}

function createCloudAuth({read, write, fetcher = fetch, now = () => Date.now()}) {
  let tail = Promise.resolve();
  const exclusive = work => {
    const next = tail.then(work, work);
    tail = next.catch(() => {});
    return next;
  };
  function status() {
    const {cloudConfig, cloudSession} = read();
    return {configured: !!cloudConfig, projectUrl: cloudConfig?.url || PROJECT,
      signedIn: !!cloudSession, email: cloudSession?.user?.email || '',
      userId: cloudSession?.user?.id || '', expiresAt: cloudSession?.expires_at || null};
  }
  function saveSession(session) { write({...read(), cloudSession: session}); }
  async function request(route, body, accessToken) {
    const config = validateCloudConfig(read().cloudConfig);
    let response;
    try {
      response = await fetcher(config.url + route, {method: 'POST', redirect: 'error',
        signal: AbortSignal.timeout(30000), headers: {'Content-Type': 'application/json',
          apikey: config.publishableKey, ...(accessToken ? {Authorization: `Bearer ${accessToken}`} : {})},
        ...(body === undefined ? {} : {body: JSON.stringify(body)})});
    } catch { throw Error('The shared workspace is unreachable. Check your connection and try again.'); }
    if (!response.ok) {
      const error = Error(response.status === 429 ? 'Too many sign-in requests. Wait briefly before trying again.' :
        [400, 401, 403].includes(response.status) ? 'Sign-in or workspace access was rejected. Check your account and permissions.' :
        'The shared workspace could not complete the request. Try again shortly.');
      error.status = response.status;
      throw error;
    }
    if (response.status === 204) return null;
    try { return await response.json(); }
    catch { throw Error('The shared workspace returned an invalid response. Please try again.'); }
  }
  function storeAuthResponse(value) {
    if (!value || typeof value.access_token !== 'string' || value.access_token.length > 16384 ||
        !/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(value.access_token) ||
        typeof value.refresh_token !== 'string' || !value.refresh_token || value.refresh_token.length > 4096 ||
        !UUID.test(value.user?.id || '') || typeof value.user?.email !== 'string' ||
        !Number.isFinite(value.expires_in) || value.expires_in <= 0 || value.expires_in > 86400) {
      throw Error('Sign-in response could not be verified. No session was saved.');
    }
    const session = {access_token: value.access_token, refresh_token: value.refresh_token,
      expires_at: Math.floor(now() / 1000) + value.expires_in,
      user: {id: value.user.id, email: value.user.email}};
    // Persist rotating credentials before acknowledging sign-in/refresh.
    saveSession(session);
    return session;
  }
  async function token() {
    const session = read().cloudSession;
    if (!session) throw Error('Sign in to your shared workspace first.');
    if (session.expires_at > now() / 1000 + 60) return session.access_token;
    try { return storeAuthResponse(await request('/auth/v1/token?grant_type=refresh_token', {refresh_token: session.refresh_token})).access_token; }
    catch (error) {
      if ([400, 401, 403].includes(error.status)) saveSession(null);
      throw error;
    }
  }
  return {
    status,
    configure: input => exclusive(async () => {
      const config = validateCloudConfig(input);
      const previous = read();
      if (JSON.stringify(config) !== JSON.stringify(previous.cloudConfig)) {
        write({...previous, cloudConfig: config, cloudSession: null, cloudWorkspace: null, cloudWorkspaceDraft: null});
      }
      return status();
    }),
    signIn: input => exclusive(async () => {
      if (!input || typeof input.email !== 'string' || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(input.email.trim()) ||
          input.email.length > 320 || typeof input.password !== 'string' || !input.password || input.password.length > 4096) {
        throw Error('Enter your workspace email and password.');
      }
      storeAuthResponse(await request('/auth/v1/token?grant_type=password', {email: input.email.trim(), password: input.password}));
      return status();
    }),
    accessToken: () => exclusive(token),
    createWorkspace: ({name, queueScope}) => exclusive(async () => {
      if (typeof name !== 'string' || !name.trim() || name.length > 100 ||
          typeof queueScope !== 'string' || !queueScope || queueScope.length > 2048) throw Error('Workspace name and queue scope are required.');
      const access = await token();
      const existing = verifiedWorkspaces(await request('/rest/v1/rpc/tv_list_workspaces', {}, access));
      const matched = existing.find(row=>row.queue_scope===queueScope);
      if (matched) return {id:matched.id,existing:true};
      let draft = read().cloudWorkspaceDraft;
      if (!draft || draft.name !== name || draft.queueScope !== queueScope || draft.userId !== read().cloudSession.user.id) {
        draft={id:randomUUID(),name,queueScope,userId:read().cloudSession.user.id};
        write({...read(),cloudWorkspaceDraft:draft});
      }
      const id=await request('/rest/v1/rpc/tv_create_workspace', {p_workspace:draft.id,p_name:name,p_queue_scope:queueScope},access);
      if(id!==draft.id)throw Error('Workspace creation receipt could not be verified. Retry will use the same identifier.');
      return {id,existing:false};
    }),
    listWorkspaces: () => exclusive(async () => {
      return verifiedWorkspaces(await request('/rest/v1/rpc/tv_list_workspaces', {}, await token()));
    }),
    signOut: () => exclusive(async () => {
      const session = read().cloudSession;
      let remoteRevoked = !session;
      try {
        if (session) {
          await request('/auth/v1/logout?scope=local', undefined, session.access_token);
          remoteRevoked = true;
        }
      } catch { /* Local removal still succeeds when the service is offline. */ }
      saveSession(null);
      return {...status(), remoteRevoked};
    }),
  };
}

module.exports = {PROJECT, validateCloudConfig, createCloudAuth};
