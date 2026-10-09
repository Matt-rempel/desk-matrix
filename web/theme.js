// Theme: "system" (default), "light" or "dark". Loaded before the stylesheet
// so the page never flashes the wrong colors; app.js uses window.deskTheme.
(function () {
  var KEY = 'desk-matrix-theme';
  var CHOICES = ['system', 'light', 'dark'];
  var media = window.matchMedia('(prefers-color-scheme: light)');

  function choice() {
    var value = null;
    try { value = localStorage.getItem(KEY); } catch (e) { /* private mode */ }
    return CHOICES.indexOf(value) >= 0 ? value : 'system';
  }

  function apply() {
    var pref = choice();
    var theme = pref === 'system' ? (media.matches ? 'light' : 'dark') : pref;
    var root = document.documentElement;
    root.setAttribute('data-theme', theme);
    root.setAttribute('data-theme-choice', pref);
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', theme === 'light' ? '#F6F5F2' : '#0B0B0C');
    document.dispatchEvent(new CustomEvent('themechange', { detail: { choice: pref, theme: theme } }));
  }

  function set(pref) {
    try {
      if (pref === 'system') localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, pref);
    } catch (e) { /* the choice lasts until reload */ }
    apply();
  }

  if (media.addEventListener) media.addEventListener('change', apply);
  else if (media.addListener) media.addListener(apply);
  apply();
  window.deskTheme = { choice: choice, set: set, choices: CHOICES };
})();
