/**
 * PDAS frontend entrypoint. Wires the login/logout controls and shared UI
 * chrome, then loads only the domain module needed for the current role.
 */

import { bindLoginForm, bindLogoutButton } from './core/auth.js';
import { refreshUserBadge, bindReauthModal } from './core/ui.js';

export const ROLE_MODULE_LOADERS = {
  citizen: () => import('./modules/citizen.js'),
  constable: () => import('./modules/constable.js'),
  detective: () => import('./modules/detective.js'),
  station_commander: () => import('./modules/station_commander.js'),
  ipid: () => import('./modules/ipid.js'),
};

export async function init({ loadShared = () => import('./modules/shared.js') } = {}) {
  bindLoginForm(document.getElementById('loginForm'), document.getElementById('loginError'));
  bindLogoutButton(document.getElementById('logoutButton'));

  const role = document.body.dataset.role;
  const loadRoleModule = ROLE_MODULE_LOADERS[role];
  if (loadRoleModule) {
    const roleModule = await loadRoleModule();
    roleModule.init();
  }

  const sharedModule = await loadShared();
  sharedModule.init();

  refreshUserBadge();
  bindReauthModal();
}

/* istanbul ignore next -- executed only in the browser, not under test */
if (typeof window !== 'undefined' && !window.__PDAS_SKIP_AUTO_INIT__) {
  init();
}
