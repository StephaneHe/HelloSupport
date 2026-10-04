// On small screens a diagram is wider than the viewport (see .diagram-scroll): start the view
// centred on it instead of on its empty left margin. Mermaid renders asynchronously, hence the retries.
(function () {
  function centre() {
    document.querySelectorAll(".diagram-scroll").forEach(function (w) {
      if (w.dataset.centred || w.scrollWidth <= w.clientWidth + 5) return;
      if (!w.querySelector("div.mermaid")) return;  // not rendered yet
      w.scrollLeft = (w.scrollWidth - w.clientWidth) / 2;
      w.dataset.centred = "1";
    });
  }
  var n = 0, t = setInterval(function () { centre(); if (++n > 20) clearInterval(t); }, 250);
  if (window.document$) window.document$.subscribe(function () { n = 0; centre(); });  // Material instant navigation
})();
