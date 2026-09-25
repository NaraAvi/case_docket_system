/**
 * Session, token storage and role-based routing for PDAS.
 */

const TOKEN_STORAGE_KEY = 'pdasToken';
const USER_STORAGE_KEY = 'pdasUser';
const SESSION_COOKIE_MAX_AGE_SECONDS = 43200;

const ROLE_HOME_ROUTES = {
  citizen: '/citizen',
  constable: '/constable',
  detective: '/detective',
  station_commander: '/station-commander',
  ipid: '/ipid',
};

export function setSession(token, user) {
  localStorage.setItem(TOKEN_STORAGE_KEY, token);
  localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user));
  document.cookie = `pdas_session_token=${encodeURIComponent(token)}; path=/; max-age=${SESSION_COOKIE_MAX_AGE_SECONDS}; SameSite=Lax`;
  document.cookie = `pdas_user=${encodeURIComponent(JSON.stringify(user))}; path=/; max-age=${SESSION_COOKIE_MAX_AGE_SECONDS}; SameSite=Lax`;
}

export function clearSession() {
  localStorage.removeItem(TOKEN_STORAGE_KEY);
  localStorage.removeItem(USER_STORAGE_KEY);
  document.cookie = 'pdas_session_token=; path=/; max-age=0; SameSite=Lax';
  document.cookie = 'pdas_user=; path=/; max-age=0; SameSite=Lax';
}

export function getToken() {
  const token = localStorage.getItem(TOKEN_STORAGE_KEY);
  if (token) {
    return token;
  }
  const match = document.cookie.match(/(?:^|; )pdas_session_token=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : null;
}

export function getUser() {
  const raw = localStorage.getItem(USER_STORAGE_KEY);
  if (raw) {
    try {
      return JSON.parse(raw);
    } catch (error) {
      return null;
    }
  }

  const match = document.cookie.match(/(?:^|; )pdas_user=([^;]*)/);
  if (!match) {
    return null;
  }

  try {
    return JSON.parse(decodeURIComponent(match[1]));
  } catch (error) {
    return null;
  }
}

export function isAuthenticated() {
  return Boolean(getToken());
}

export function routeByRole(targetRole) {
  window.location.href = ROLE_HOME_ROUTES[targetRole] || '/login';
}

export function requireRole(expectedRole) {
  const user = getUser();
  if (!user || user.role !== expectedRole) {
    routeByRole(user ? user.role : null);
    return false;
  }
  return true;
}

export function bindLoginForm(form, errorBox, { login } = {}) {
  if (!form) {
    return;
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const idInput = document.getElementById('testId');
    const testId = idInput ? idInput.value.trim() : '';
    errorBox?.classList.add('hidden');

    try {
      const performLogin = login || (await import('./api.js')).fetchJson;
      const payload = await performLogin('/api/v1/auth/login', {
        method: 'POST',
        body: { test_id: testId },
      });

      setSession(payload.access_token, {
        full_name: payload.full_name,
        role: payload.role,
        test_id: payload.test_id,
      });

      routeByRole(payload.role);
    } catch (error) {
      if (errorBox) {
        errorBox.textContent = error.message || 'Unable to sign in.';
        errorBox.classList.remove('hidden');
      }
    }
  });
}

export function bindLogoutButton(button) {
  if (!button) {
    return;
  }
  button.addEventListener('click', () => {
    clearSession();
    window.location.href = '/login';
  });
}
