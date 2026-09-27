// Shared UI behavior: mobile sidebar toggle + flash message auto-dismiss.
document.addEventListener('DOMContentLoaded', function () {
  var sidebar = document.getElementById('sidebar');
  var backdrop = document.getElementById('sidebar-backdrop');
  var openBtn = document.getElementById('sidebar-open');
  var closeBtn = document.getElementById('sidebar-close');

  function openSidebar() {
    if (!sidebar) return;
    sidebar.classList.remove('-translate-x-full');
    if (backdrop) backdrop.classList.remove('hidden');
  }
  function closeSidebar() {
    if (!sidebar) return;
    sidebar.classList.add('-translate-x-full');
    if (backdrop) backdrop.classList.add('hidden');
  }

  if (openBtn) openBtn.addEventListener('click', openSidebar);
  if (closeBtn) closeBtn.addEventListener('click', closeSidebar);
  if (backdrop) backdrop.addEventListener('click', closeSidebar);

  // Auto-dismiss flash messages after a few seconds (success/info only —
  // errors stay until the user reads and closes them).
  document.querySelectorAll('.flash-alert').forEach(function (el) {
    var isSticky = el.className.indexOf('rose') !== -1;
    if (isSticky) return;
    setTimeout(function () {
      el.classList.add('dismissing');
      setTimeout(function () { el.remove(); }, 200);
    }, 6000);
  });

  // Any element with data-confirm="message" asks before its form submits.
  document.querySelectorAll('[data-confirm]').forEach(function (el) {
    el.addEventListener('submit', function (e) {
      if (!window.confirm(el.getAttribute('data-confirm'))) {
        e.preventDefault();
      }
    });
  });
});
