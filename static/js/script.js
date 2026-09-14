/* 杨芳清-简历：把每个条目里的图片按横竖分行
   横图行 3 列（16:9 外框），竖图行 6 列（9:16 外框），行内不混排。 */
(function () {
  "use strict";

  function sortGrids() {
    var grids = document.querySelectorAll(".igrid");
    Array.prototype.forEach.call(grids, function (grid) {
      var figs = Array.prototype.slice.call(grid.querySelectorAll("figure"));
      if (!figs.length) return;

      var land = [],
        port = [];
      figs.forEach(function (f) {
        var frame = f.querySelector(".frame");
        var o = frame ? frame.getAttribute("data-o") : "h";
        (o === "v" ? port : land).push(f);
      });

      grid.classList.add("is-sorted");
      grid.innerHTML = "";

      function addRow(cls, list) {
        if (!list.length) return;
        var row = document.createElement("div");
        row.className = "row " + cls;
        list.forEach(function (f) {
          row.appendChild(f);
        });
        grid.appendChild(row);
      }

      addRow("row-land", land);
      addRow("row-portrait", port);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", sortGrids);
  } else {
    sortGrids();
  }
})();

/* ===== image lightbox + 禁右键 ===== */
(function () {
  "use strict";
  document.addEventListener("contextmenu", function (e) { e.preventDefault(); });

  var lb = document.createElement("div");
  lb.className = "lightbox";
  lb.innerHTML = '<div class="lb-media"></div><span class="lb-hint">点击任意处关闭</span>';
  document.body.appendChild(lb);
  var lbMediaBox = lb.querySelector(".lb-media");
  function setLbMedia(src) {
    lbMediaBox.innerHTML = "";
    var isVid = /\.(mp4|m4v|mov|webm)([?#]|$)/i.test(src);
    if (isVid) {
      var v = document.createElement("video");
      v.src = src; v.controls = true; v.autoplay = true;
      v.setAttribute("playsinline", ""); v.setAttribute("preload", "metadata");
      lbMediaBox.appendChild(v);
    } else {
      var im = document.createElement("img");
      im.src = src; im.alt = "";
      lbMediaBox.appendChild(im);
    }
  }
  function openLb(src) {
    setLbMedia(src);
    lb.classList.add("show");
    document.body.style.overflow = "hidden";
  }
  function closeLb() {
    document.body.style.overflow = "";
    lb.classList.remove("show");
    lbMediaBox.innerHTML = "";
  }
  document.addEventListener("click", function (e) {
    var z = e.target.closest ? e.target.closest("a.img-zoom") : null;
    if (z) {
      e.preventDefault();
      var fig = z.closest ? z.closest("figure") : null;
      var fc = fig ? fig.querySelector("figcaption") : null;
      openLb(z.getAttribute("href"));
      return;
    }
    if (lb.classList.contains("show") && lb.contains(e.target)) closeLb();
  });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") closeLb(); });
})();


/* ===== 图片懒加载：details 展开时才真正请求图片/视频（折叠条目 0 请求） ===== */
(function () {
  "use strict";
  var items = document.querySelectorAll("details.item");
  Array.prototype.forEach.call(items, function (d) {
    d.addEventListener("toggle", function () {
      if (!d.open) return;
      var els = d.querySelectorAll("[data-src]");
      Array.prototype.forEach.call(els, function (el) {
        var s = el.getAttribute("data-src");
        if (s && !el.getAttribute("src")) el.setAttribute("src", s);
        el.removeAttribute("data-src");
      });
    });
  });
})();
