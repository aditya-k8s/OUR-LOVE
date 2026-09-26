/* Our Love - dashboard interactions: drawer, confirmations, chart, drag-and-drop uploads. */
(function () {
  "use strict";

  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  function csrfToken() {
    var input = $("input[name=csrfmiddlewaretoken]");
    return input ? input.value : "";
  }

  function formatSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / 1024 / 1024).toFixed(1) + " MB";
  }

  /* platform request limit (e.g. 4.5 MB on Vercel); 0 means no limit */
  var REQUEST_LIMIT = parseInt(document.body.dataset.requestLimit, 10) || 0;
  var RESIZE_ABOVE = 3.5 * 1024 * 1024;
  var MAX_SIDE = 3000;

  /* Re-encode large photos in the browser so they fit the request limit.
     The server re-encodes and strips metadata again, so nothing is lost but bytes. */
  function shrinkImage(file) {
    if (file.size <= RESIZE_ABOVE || !window.createImageBitmap || !/^image\/(jpeg|png|webp)$/.test(file.type)) {
      return Promise.resolve(file);
    }
    return createImageBitmap(file, { imageOrientation: "from-image" }).then(function (bitmap) {
      var scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
      var canvas = document.createElement("canvas");
      canvas.width = Math.round(bitmap.width * scale);
      canvas.height = Math.round(bitmap.height * scale);
      canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      return new Promise(function (resolve) {
        canvas.toBlob(function (blob) {
          if (!blob || blob.size >= file.size) { resolve(file); return; }
          var name = file.name.replace(/\.(png|webp|jpe?g)$/i, "") + ".jpg";
          resolve(new File([blob], name, { type: "image/jpeg", lastModified: file.lastModified }));
        }, "image/jpeg", 0.88);
      });
    }).catch(function () { return file; });
  }

  /* Plain file inputs on forms: shrink photos in place and warn about oversize requests. */
  function initFileInputs() {
    $$("form input[type=file]").forEach(function (input) {
      if (input.hasAttribute("data-dropzone-input")) return;
      var note = document.createElement("p");
      note.className = "help";
      note.setAttribute("role", "status");
      input.after(note);
      input.addEventListener("change", function () {
        var files = Array.prototype.slice.call(input.files || []);
        note.textContent = "";
        if (!files.length) return;
        var isImage = /image/.test(input.accept || "");
        Promise.all(files.map(function (f) { return isImage ? shrinkImage(f) : Promise.resolve(f); })).then(function (ready) {
          if (window.DataTransfer && ready.some(function (f, i) { return f !== files[i]; })) {
            var dt = new DataTransfer();
            ready.forEach(function (f) { dt.items.add(f); });
            input.files = dt.files;
          }
          var total = ready.reduce(function (sum, f) { return sum + f.size; }, 0);
          if (REQUEST_LIMIT && total > REQUEST_LIMIT * 0.95) {
            note.textContent = "These files total " + formatSize(total) + ", more than this server accepts in one request (" +
              formatSize(REQUEST_LIMIT) + "). " + (isImage ? "Upload fewer at a time, or use the Photos page." :
              "For large chat exports use: python manage.py import_chat_history <file>");
            note.classList.add("errorlist");
          }
        });
      });
    });
  }

  /* drawer (mobile navigation) */
  function initDrawer() {
    var drawer = $("[data-drawer]");
    if (!drawer) return;
    $$("[data-drawer-open]").forEach(function (b) { b.addEventListener("click", function () { drawer.classList.add("is-open"); }); });
    $$("[data-drawer-close]").forEach(function (b) { b.addEventListener("click", function () { drawer.classList.remove("is-open"); }); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") drawer.classList.remove("is-open"); });
  }

  /* confirmations on destructive forms / buttons */
  function initConfirm() {
    document.addEventListener("submit", function (e) {
      var form = e.target;
      var submitter = e.submitter;
      var message = (submitter && submitter.dataset.confirm) || form.dataset.confirm;
      if (message && !window.confirm(message)) e.preventDefault();
    });
  }

  /* chart bar heights (set from data attributes; CSP forbids inline styles) */
  function initChart() {
    $$(".chart-bar[data-height]").forEach(function (bar) {
      bar.style.height = Math.max(parseInt(bar.dataset.height, 10) || 0, 1) + "%";
    });
  }

  /* drag-and-drop uploader: one XHR per file so each has its own progress */
  var IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];
  var VIDEO_TYPES = ["video/mp4", "video/webm"];

  function initDropzones() {
    $$("[data-dropzone]").forEach(function (zone) {
      var input = $("[data-dropzone-input]", zone);
      var list = zone.parentElement.querySelector("[data-uploads]");
      var kind = zone.dataset.kind;
      var url = zone.dataset.uploadUrl;
      var queue = [];
      var active = 0;
      var MAX_PARALLEL = 3;
      var uploaded = 0;
      var pendingPrep = 0;

      ["dragenter", "dragover"].forEach(function (evt) {
        zone.addEventListener(evt, function (e) { e.preventDefault(); zone.classList.add("is-over"); });
      });
      ["dragleave", "drop"].forEach(function (evt) {
        zone.addEventListener(evt, function (e) { e.preventDefault(); zone.classList.remove("is-over"); });
      });
      zone.addEventListener("drop", function (e) { addFiles(e.dataTransfer.files); });
      input.addEventListener("change", function () { addFiles(input.files); input.value = ""; });

      function addFiles(files) {
        Array.prototype.forEach.call(files, function (file) {
          var row = document.createElement("li");
          row.className = "upload";
          row.innerHTML = '<div class="preview"></div><div><div class="name"></div><div class="size"></div><div class="bar"><span></span></div></div><span class="status">Waiting</span>';
          $(".name", row).textContent = file.name;
          $(".size", row).textContent = formatSize(file.size);
          list.appendChild(row);
          var allowed = kind === "photo" ? IMAGE_TYPES : VIDEO_TYPES;
          if (allowed.indexOf(file.type) === -1) {
            fail(row, kind === "photo" ? "Only JPG, PNG or WEBP" : "Only MP4 or WebM");
            return;
          }
          if (kind === "photo") {
            var img = document.createElement("img");
            img.alt = "";
            img.src = URL.createObjectURL(file);
            img.onload = function () { URL.revokeObjectURL(img.src); };
            $(".preview", row).appendChild(img);
          }
          var prepared = kind === "photo" ? shrinkImage(file) : Promise.resolve(file);
          pendingPrep += 1;
          prepared.then(function (ready) {
            pendingPrep -= 1;
            if (REQUEST_LIMIT && ready.size > REQUEST_LIMIT * 0.97) {
              fail(row, kind === "photo" ? "Too large for this server even after resizing" :
                "Larger than " + formatSize(REQUEST_LIMIT) + " (server limit). Add it as a video link instead.");
              return;
            }
            if (ready !== file) $(".size", row).textContent = formatSize(file.size) + " to " + formatSize(ready.size);
            queue.push({ file: ready, row: row });
            pump();
          });
        });
      }

      function fail(row, message) {
        row.classList.add("is-error");
        $(".status", row).textContent = message;
      }

      function pump() {
        while (active < MAX_PARALLEL && queue.length) {
          active += 1;
          send(queue.shift());
        }
      }

      function send(job) {
        var xhr = new XMLHttpRequest();
        var data = new FormData();
        data.append("file", job.file);
        xhr.open("POST", url);
        xhr.setRequestHeader("X-CSRFToken", csrfToken());
        xhr.setRequestHeader("Accept", "application/json");
        xhr.upload.addEventListener("progress", function (e) {
          if (e.lengthComputable) {
            var pct = Math.round((e.loaded / e.total) * 100);
            $(".bar span", job.row).style.width = pct + "%";
            $(".status", job.row).textContent = pct < 100 ? pct + "%" : "Processing";
          }
        });
        xhr.addEventListener("load", function () {
          var body = {};
          try { body = JSON.parse(xhr.responseText); } catch (e) { /* not JSON */ }
          if (xhr.status >= 200 && xhr.status < 300 && body.ok) {
            job.row.classList.add("is-done");
            $(".bar span", job.row).style.width = "100%";
            var link = document.createElement("a");
            link.href = body.edit;
            link.textContent = "Add details";
            var status = $(".status", job.row);
            status.textContent = "";
            status.appendChild(link);
            if (body.thumb && !$(".preview img", job.row)) {
              var img = document.createElement("img");
              img.src = body.thumb; img.alt = "";
              $(".preview", job.row).appendChild(img);
            }
            uploaded += 1;
          } else {
            fail(job.row, body.error || (xhr.status === 413 ? "File too large" : "Upload failed"));
          }
          done();
        });
        xhr.addEventListener("error", function () { fail(job.row, "Network error"); done(); });
        xhr.send(data);
      }

      function done() {
        active -= 1;
        pump();
        if (!active && !queue.length && !pendingPrep && uploaded) {
          var note = zone.parentElement.querySelector("[data-reload]");
          if (!note) {
            note = document.createElement("p");
            note.className = "help muted";
            note.setAttribute("data-reload", "");
            note.innerHTML = '<a href="">Refresh</a> to see new uploads below.';
            list.after(note);
          }
        }
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initDrawer();
    initConfirm();
    initChart();
    initDropzones();
    initFileInputs();
  });
})();
