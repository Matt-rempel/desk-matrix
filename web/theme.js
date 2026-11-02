// Follow the device appearance. Loaded before the stylesheet to avoid a flash
// of the wrong colors. Old manual preferences no longer override the system.
(function () {
  var media = window.matchMedia('(prefers-color-scheme: light)');

  function apply() {
    var theme = media.matches ? 'light' : 'dark';
    var root = document.documentElement;
    root.setAttribute('data-theme', theme);
    root.setAttribute('data-theme-choice', 'system');
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', theme === 'light' ? '#F6F5F2' : '#0B0B0C');
    document.dispatchEvent(new CustomEvent('themechange', { detail: { choice: 'system', theme: theme } }));
  }

  if (media.addEventListener) media.addEventListener('change', apply);
  else if (media.addListener) media.addListener(apply);
  apply();
})();
