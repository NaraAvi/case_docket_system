/**
 * Collapsible sidebar. The toggle lives in base.html's brand block; the
 * collapsed state is a class on `.pdas-shell` (CSS sets --sidebar-w) and is
 * remembered in localStorage, which may be unavailable.
 */

const NAV_STORAGE_KEY = 'pdasNavCollapsed';

function readCollapsed() {
  try {
    return localStorage.getItem(NAV_STORAGE_KEY) === '1';
  } catch (error) {
    return false;
  }
}

function writeCollapsed(collapsed) {
  try {
    localStorage.setItem(NAV_STORAGE_KEY, collapsed ? '1' : '0');
  } catch (error) {
    // storage unavailable -- the preference simply isn't remembered.
  }
}

export function initNav() {
  const shell = document.querySelector('.pdas-shell');
  const toggle = document.getElementById('navToggle');
  if (!shell || !toggle) {
    return;
  }
  const apply = (collapsed) => {
    shell.classList.toggle('nav-collapsed', collapsed);
    toggle.setAttribute('aria-expanded', String(!collapsed));
    const label = collapsed ? 'Expand navigation' : 'Collapse navigation';
    toggle.setAttribute('aria-label', label);
    toggle.title = label;
  };
  apply(readCollapsed());
  toggle.addEventListener('click', () => {
    const collapsed = !shell.classList.contains('nav-collapsed');
    apply(collapsed);
    writeCollapsed(collapsed);
  });
}
