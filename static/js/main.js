// ===== Nerve Rail (Landing Page) =====
(function() {
  var rail = document.querySelector('.nerve-rail-line');
  var dot = document.querySelector('.nerve-rail-dot');
  if (!rail) return;

  function update() {
    var scrollY = window.scrollY;
    var docHeight = document.documentElement.scrollHeight - window.innerHeight;
    var progress = docHeight > 0 ? Math.min(scrollY / docHeight, 1) : 0;
    var railHeight = rail.offsetHeight;

    if (dot) {
      dot.style.top = (progress * (railHeight - 10)) + 'px';
      var colors = ['#4ade80', '#38bdf8', '#f59e0b', '#a855f7', '#4ade80'];
      var idx = Math.min(Math.floor(progress * colors.length), colors.length - 1);
      dot.style.background = colors[idx];
      dot.style.boxShadow = '0 0 8px ' + colors[idx];
    }

    var nodes = document.querySelectorAll('.nerve-rail-node');
    if (nodes.length > 1) {
      nodes.forEach(function(node, i) {
        node.classList.toggle('active', progress >= (i / (nodes.length - 1)) - 0.05);
      });
    }
  }

  window.addEventListener('scroll', update);
  window.addEventListener('resize', update);
  update();
})();

// ===== Navbar Scroll =====
(function() {
  var nav = document.querySelector('nav');
  if (!nav) return;
  window.addEventListener('scroll', function() {
    nav.classList.toggle('scrolled', window.scrollY > 60);
  });
})();

// ===== Escape Helpers =====
function escapeHtml(str) {
  var div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function encodeData(str) {
  return encodeURIComponent(str);
}

function decodeData(str) {
  try { return decodeURIComponent(str); } catch(e) { return str; }
}

function getCsrfToken() {
  var meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.getAttribute('content') : '';
}

// ===== Load User Settings =====
(function() {
  var script = document.getElementById('userSettings');
  if (!script) return;
  var s;
  try { s = JSON.parse(script.textContent); } catch(e) { return; }

  var modeTabs = document.querySelectorAll('.mode-tab');
  if (s.default_mode === 'detection' && modeTabs.length > 1) {
    modeTabs.forEach(function(t) { t.classList.remove('active'); });
    var dt = Array.from(modeTabs).find(function(t) { return t.dataset.mode === 'detection'; });
    if (dt) dt.classList.add('active');
  }
  if (s.default_mode === 'barcode') {
    modeTabs.forEach(function(t) { t.classList.remove('active'); });
    var bt = Array.from(modeTabs).find(function(t) { return t.dataset.mode === 'barcode'; });
    if (bt) bt.classList.add('active');
  }

  var gs = document.getElementById('grayscaleToggle');
  if (gs && s.default_grayscale !== undefined) gs.checked = s.default_grayscale;

  var dk = document.getElementById('deskewToggle');
  if (dk && s.default_deskew !== undefined) dk.checked = s.default_deskew;

  var bk = document.getElementById('blurKernel');
  var bd = document.getElementById('blurDisplay');
  if (bk && s.default_blur_kernel) { bk.value = s.default_blur_kernel; if (bd) bd.textContent = s.default_blur_kernel; }

  var tm = document.getElementById('thresholdMethod');
  if (tm && s.default_threshold_method) tm.value = s.default_threshold_method;

  var tb = document.getElementById('thresholdBlock');
  var tbd = document.getElementById('blockDisplay');
  if (tb && s.default_threshold_block) { tb.value = s.default_threshold_block; if (tbd) tbd.textContent = s.default_threshold_block; }

  var tc = document.getElementById('thresholdC');
  var tcd = document.getElementById('cDisplay');
  if (tc && s.default_threshold_c) { tc.value = s.default_threshold_c; if (tcd) tcd.textContent = s.default_threshold_c; }

  var lang = document.getElementById('ocrLang');
  if (lang && s.default_lang) lang.value = s.default_lang;

  var psm = document.getElementById('ocrPsm');
  if (psm && s.default_psm) psm.value = s.default_psm;

  var br = document.getElementById('brightness');
  var brd = document.getElementById('brightnessDisplay');
  if (br && s.default_brightness !== undefined) { br.value = s.default_brightness; if (brd) brd.textContent = s.default_brightness; }

  var cr = document.getElementById('contrast');
  var crd = document.getElementById('contrastDisplay');
  if (cr && s.default_contrast !== undefined) { cr.value = s.default_contrast; if (crd) crd.textContent = s.default_contrast; }
})();

// ===== Dark Mode =====
(function() {
  var toggle = document.getElementById('themeToggle');
  if (!toggle) return;

  var stored = localStorage.getItem('decodelabs-theme');
  var isDark = stored === 'dark';
  if (isDark) {
    document.documentElement.setAttribute('data-theme', 'dark');
  }
  toggle.textContent = isDark ? '☀️' : '🌙';

  toggle.addEventListener('click', function() {
    var dark = document.documentElement.getAttribute('data-theme') === 'dark';
    if (dark) {
      document.documentElement.removeAttribute('data-theme');
      localStorage.setItem('decodelabs-theme', 'light');
      toggle.textContent = '🌙';
    } else {
      document.documentElement.setAttribute('data-theme', 'dark');
      localStorage.setItem('decodelabs-theme', 'dark');
      toggle.textContent = '☀️';
    }
  });
})();

// ===== App Toolkit =====
(function() {
  var uploadZone = document.getElementById('uploadZone');
  var fileInput = document.getElementById('fileInput');
  var batchInput = document.getElementById('batchInput');
  var modeTabs = document.querySelectorAll('.mode-tab');
  var resultArea = document.getElementById('resultArea');
  var previewArea = document.getElementById('previewArea');
  var preprocessPanel = document.getElementById('preprocessPanel');
  var togglePreprocess = document.getElementById('togglePreprocess');
  var loadingOverlay = document.getElementById('loadingOverlay');
  var historyList = document.getElementById('historyList');
  var historyEmpty = document.getElementById('historyEmpty');
  var clearHistory = document.getElementById('clearHistory');
  var webcamBtn = document.getElementById('webcamBtn');
  var webcamSection = document.getElementById('webcamSection');
  var batchBtn = document.getElementById('batchBtn');
  var loadMoreBtn = document.getElementById('loadMoreHistory');

  var currentMode = 'ocr';
  var webcamStream = null;
  var historyOffset = 0;
  var historyLimit = 20;

  if (!uploadZone) return;

  // ===== Mode Switching =====
  modeTabs.forEach(function(tab) {
    tab.addEventListener('click', function() {
      // Close webcam when switching modes
      if (webcamStream) {
        closeWebcamFn();
      }
      modeTabs.forEach(function(t) { t.classList.remove('active'); });
      this.classList.add('active');
      currentMode = this.dataset.mode;

      // Show/hide OCR-specific controls
      var langGroup = document.getElementById('langGroup');
      if (langGroup) {
        langGroup.style.display = currentMode === 'ocr' ? 'flex' : 'none';
      }
      var psmGroup = document.getElementById('psmGroup');
      if (psmGroup) {
        psmGroup.style.display = currentMode === 'ocr' ? 'flex' : 'none';
      }
      var threshGroup = document.getElementById('thresholdGroup');
      if (threshGroup) {
        threshGroup.style.display = (currentMode === 'ocr') ? 'flex' : 'none';
      }
      var threshMethod = document.getElementById('thresholdMethod');
      var isAdaptive = threshMethod && threshMethod.value === 'adaptive';
      var threshBlockGroup = document.getElementById('thresholdBlockGroup');
      if (threshBlockGroup) {
        threshBlockGroup.style.display = (currentMode === 'ocr' && isAdaptive) ? 'flex' : 'none';
      }
      var threshCGroup = document.getElementById('thresholdCGroup');
      if (threshCGroup) {
        threshCGroup.style.display = (currentMode === 'ocr' && isAdaptive) ? 'flex' : 'none';
      }

      if (resultArea) resultArea.classList.remove('visible');
      if (previewArea) previewArea.classList.remove('visible');
    });
  });

  // ===== Preprocessing Toggle =====
  if (togglePreprocess) {
    togglePreprocess.addEventListener('click', function() {
      preprocessPanel.classList.toggle('visible');
      this.textContent = preprocessPanel.classList.contains('visible')
        ? '⚙ Hide Preprocessing' : '⚙ Show Preprocessing';
    });
  }

  // ===== Range Slider Values =====
  document.querySelectorAll('input[type="range"]').forEach(function(slider) {
    var display = document.getElementById(slider.dataset.display);
    if (display) {
      slider.addEventListener('input', function() {
        display.textContent = this.value;
      });
    }
  });

  // ===== Threshold method toggle =====
  var threshMethod = document.getElementById('thresholdMethod');
  if (threshMethod) {
    threshMethod.addEventListener('change', function() {
      var isAdaptive = this.value === 'adaptive';
      var blockGroup = document.getElementById('thresholdBlockGroup');
      var cGroup = document.getElementById('thresholdCGroup');
      if (blockGroup) blockGroup.style.display = isAdaptive ? 'flex' : 'none';
      if (cGroup) cGroup.style.display = isAdaptive ? 'flex' : 'none';
    });
  }

  // ===== Presets =====
  var presetSelect = document.getElementById('presetSelect');
  var savePresetBtn = document.getElementById('savePreset');
  var deletePresetBtn = document.getElementById('deletePreset');

  if (presetSelect) {
    loadPresets();

    presetSelect.addEventListener('change', function() {
      var name = this.value;
      if (!name) return;
      var presets;
      try { presets = JSON.parse(localStorage.getItem('decodelabs-presets') || '{}'); } catch(e) { presets = {}; }
      var p = presets[name];
      if (!p) return;
      document.getElementById('grayscaleToggle').checked = p.grayscale;
      document.getElementById('deskewToggle').checked = p.deskew;
      document.getElementById('blurKernel').value = p.blur_kernel;
      var bd = document.getElementById('blurDisplay');
      if (bd) bd.textContent = p.blur_kernel;
      document.getElementById('thresholdMethod').value = p.threshold_method;
      document.getElementById('thresholdBlock').value = p.threshold_block;
      var tbd = document.getElementById('blockDisplay');
      if (tbd) tbd.textContent = p.threshold_block;
      document.getElementById('thresholdC').value = p.threshold_c;
      var tcd = document.getElementById('cDisplay');
      if (tcd) tcd.textContent = p.threshold_c;
      if (p.lang) {
        var langSel = document.getElementById('ocrLang');
        if (langSel) langSel.value = p.lang;
      }
      if (p.brightness !== undefined) {
        var br = document.getElementById('brightness');
        var brd = document.getElementById('brightnessDisplay');
        if (br) { br.value = p.brightness; if (brd) brd.textContent = p.brightness; }
      }
      if (p.contrast !== undefined) {
        var cr = document.getElementById('contrast');
        var crd = document.getElementById('contrastDisplay');
        if (cr) { cr.value = p.contrast; if (crd) crd.textContent = p.contrast; }
      }
      if (p.psm) {
        var psmSel = document.getElementById('ocrPsm');
        if (psmSel) psmSel.value = p.psm;
      }
    });

    if (savePresetBtn) {
      savePresetBtn.addEventListener('click', function() {
        var name = prompt('Preset name:');
        if (!name) return;
        var presets;
        try { presets = JSON.parse(localStorage.getItem('decodelabs-presets') || '{}'); } catch(e) { presets = {}; }
        presets[name] = {
          grayscale: document.getElementById('grayscaleToggle').checked,
          deskew: document.getElementById('deskewToggle').checked,
          blur_kernel: parseInt(document.getElementById('blurKernel').value),
          threshold_method: document.getElementById('thresholdMethod').value,
          threshold_block: parseInt(document.getElementById('thresholdBlock').value),
          threshold_c: parseInt(document.getElementById('thresholdC').value),
          lang: document.getElementById('ocrLang') ? document.getElementById('ocrLang').value : 'eng',
          psm: document.getElementById('ocrPsm') ? document.getElementById('ocrPsm').value : '6',
          brightness: parseInt(document.getElementById('brightness') ? document.getElementById('brightness').value : 0),
          contrast: parseInt(document.getElementById('contrast') ? document.getElementById('contrast').value : 0)
        };
        localStorage.setItem('decodelabs-presets', JSON.stringify(presets));
        loadPresets();
        presetSelect.value = name;
      });
    }

    if (deletePresetBtn) {
      deletePresetBtn.addEventListener('click', function() {
        var name = presetSelect.value;
        if (!name) return;
        var presets;
        try { presets = JSON.parse(localStorage.getItem('decodelabs-presets') || '{}'); } catch(e) { presets = {}; }
        delete presets[name];
        localStorage.setItem('decodelabs-presets', JSON.stringify(presets));
        loadPresets();
      });
    }
  }

  function loadPresets() {
    var presets;
    try { presets = JSON.parse(localStorage.getItem('decodelabs-presets') || '{}'); } catch(e) { presets = {}; }
    var names = Object.keys(presets);
    presetSelect.innerHTML = '<option value="">Load Preset...</option>';
    names.forEach(function(n) {
      var opt = document.createElement('option');
      opt.value = n;
      opt.textContent = n;
      presetSelect.appendChild(opt);
    });
  }

  // ===== Upload Zone =====
  uploadZone.addEventListener('click', function(e) {
    if (e.target.tagName !== 'INPUT') fileInput.click();
  });

  uploadZone.addEventListener('dragover', function(e) {
    e.preventDefault();
    this.classList.add('dragover');
  });

  uploadZone.addEventListener('dragleave', function(e) {
    e.preventDefault();
    if (e.target === this) this.classList.remove('dragover');
  });

  uploadZone.addEventListener('drop', function(e) {
    e.preventDefault();
    this.classList.remove('dragover');
    if (e.dataTransfer.files.length) processFile(e.dataTransfer.files[0]);
  });

  fileInput.addEventListener('change', function() {
    if (this.files.length) processFile(this.files[0]);
  });

  // ===== Batch Upload =====
  if (batchBtn) {
    batchBtn.addEventListener('click', function() {
      batchInput.click();
    });
  }

  if (batchInput) {
    batchInput.addEventListener('change', function() {
      if (!this.files.length) return;
      processBatch(this.files);
    });
  }

  // ===== Webcam =====
  if (webcamBtn) {
    webcamBtn.addEventListener('click', function() {
      toggleWebcam();
    });
  }

  var closeWebcamBtn = document.getElementById('closeWebcam');
  if (closeWebcamBtn) {
    closeWebcamBtn.addEventListener('click', function() {
      closeWebcamFn();
    });
  }

  function toggleWebcam() {
    if (!webcamSection) return;
    if (webcamSection.classList.contains('visible')) {
      closeWebcamFn();
      return;
    }
    webcamSection.classList.add('visible');
    webcamBtn.textContent = '✕ Close Camera';
    startWebcam();
  }

  function closeWebcamFn() {
    stopWebcam();
    webcamSection.classList.remove('visible');
    if (webcamBtn) webcamBtn.textContent = '📷 Camera';
  }

  function startWebcam() {
    var video = document.getElementById('webcamVideo');
    if (!video) return;
    var constraints = { video: true };
    navigator.mediaDevices.getUserMedia(constraints)
      .then(function(stream) {
        webcamStream = stream;
        video.srcObject = stream;
        video.play();
      })
      .catch(function(err) {
        alert('Camera access denied: ' + err.message);
        webcamSection.classList.remove('visible');
        webcamBtn.textContent = '📷 Camera';
      });
  }

  function stopWebcam() {
    if (webcamStream) {
      webcamStream.getTracks().forEach(function(t) { t.stop(); });
      webcamStream = null;
    }
    var video = document.getElementById('webcamVideo');
    if (video) video.srcObject = null;
  }

  // Capture from webcam
  var captureBtn = document.getElementById('captureBtn');
  if (captureBtn) {
    captureBtn.addEventListener('click', function() {
      var video = document.getElementById('webcamVideo');
      var canvas = document.createElement('canvas');
      canvas.width = video.videoWidth || 640;
      canvas.height = video.videoHeight || 480;
      var ctx = canvas.getContext('2d');
      ctx.drawImage(video, 0, 0);
      var b64 = canvas.toDataURL('image/png');
      stopWebcam();
      webcamSection.classList.remove('visible');
      webcamBtn.textContent = '📷 Camera';
      uploadBase64(b64);
    });
  }

  function uploadBase64(b64) {
    var formData = new FormData();
    formData.append('image_b64', b64);
    formData.append('mode', currentMode);
    appendPreprocessParams(formData);
    showLoading();
    fetch('/upload', { method: 'POST', body: formData })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        hideLoading();
        if (data.error) { showError(data.error); return; }
        showResult(data);
        loadHistory();
      })
      .catch(function(err) {
        hideLoading();
        showError('Error: ' + err.message);
      });
  }

  // ===== Clipboard Paste =====
  document.addEventListener('paste', function(e) {
    if (!uploadZone) return;
    var items = e.clipboardData.items;
    for (var i = 0; i < items.length; i++) {
      if (items[i].type.startsWith('image/')) {
        var blob = items[i].getAsFile();
        if (blob) {
          showClipboardNotif();
          processFile(blob);
        }
        break;
      }
    }
  });

  function showClipboardNotif() {
    var el = document.getElementById('clipboardNotif');
    if (!el) return;
    el.classList.add('visible');
    setTimeout(function() { el.classList.remove('visible'); }, 2000);
  }

  // ===== Rotation =====
  var rotateLeft = document.getElementById('rotateLeft');
  var rotateRight = document.getElementById('rotateRight');

  if (rotateLeft) {
    rotateLeft.addEventListener('click', function() {
      var inp = document.getElementById('rotationInput');
      if (inp) inp.value = '-90';
      rotateImagePreview();
    });
  }
  if (rotateRight) {
    rotateRight.addEventListener('click', function() {
      var inp = document.getElementById('rotationInput');
      if (inp) inp.value = '90';
      rotateImagePreview();
    });
  }

  function rotateImagePreview() {
    var inp = document.getElementById('rotationInput');
    if (!inp || !inp.value) return;
    var deg = inp.value === '-90' ? -90 : (inp.value === '90' ? 90 : (inp.value === '180' ? 180 : 0));
    var previewImgs = document.querySelectorAll('.preview-image, .comparison-container img');
    previewImgs.forEach(function(img) {
      if (img.src && !img.src.startsWith('data:image/png;base64,')) return;
      img.style.transform = 'rotate(' + deg + 'deg)';
      img.style.transition = 'transform 0.3s ease';
    });
  }

  // ===== History =====
  loadHistory();

  if (loadMoreBtn) {
    loadMoreBtn.addEventListener('click', function() {
      loadMoreHistory();
    });
  }

  if (clearHistory) {
    clearHistory.addEventListener('click', function() {
      if (!confirm('Are you sure you want to clear all history?')) return;
      fetch('/clear_history', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ _csrf_token: getCsrfToken() })
      })
        .then(function(r) {
          if (!r.ok) { showError('Failed to clear history'); return; }
          historyList.innerHTML = '';
          historyEmpty.style.display = 'block';
          historyOffset = 0;
          if (loadMoreBtn) loadMoreBtn.style.display = 'none';
        })
        .catch(function() {
          showError('Failed to clear history due to network error');
        });
    });
  }

  function loadHistory() {
    historyOffset = 0;
    fetch('/history?limit=' + historyLimit + '&offset=0')
      .then(function(r) { return r.json(); })
      .then(function(items) {
        historyList.innerHTML = '';
        if (!items.length) {
          historyEmpty.style.display = 'block';
          if (loadMoreBtn) loadMoreBtn.style.display = 'none';
          return;
        }
        historyEmpty.style.display = 'none';
        items.forEach(function(item) {
          appendHistoryItem(item);
        });
        historyOffset = items.length;
        if (loadMoreBtn) loadMoreBtn.style.display = items.length < historyLimit ? 'none' : 'block';
        fetch('/history_count').then(function(r) { return r.json(); }).then(function(count) {
          if (loadMoreBtn && historyOffset >= count) loadMoreBtn.style.display = 'none';
        });
      });
  }

  function loadMoreHistory() {
    fetch('/history?limit=' + historyLimit + '&offset=' + historyOffset)
      .then(function(r) { return r.json(); })
      .then(function(items) {
        if (!items.length) {
          if (loadMoreBtn) loadMoreBtn.style.display = 'none';
          return;
        }
        items.forEach(function(item) {
          appendHistoryItem(item);
        });
        historyOffset += items.length;
        if (items.length < historyLimit) {
          if (loadMoreBtn) loadMoreBtn.style.display = 'none';
        }
      });
  }

  function appendHistoryItem(item) {
    var el = document.createElement('div');
    el.className = 'history-item';
    var modeIcon = item.mode === 'ocr' ? '🔤 OCR' : (item.mode === 'barcode' ? '📶 Barcode' : '🎯 Detection');
    el.innerHTML =
      '<div class="h-mode">' + modeIcon + '</div>' +
      '<div class="h-file">' + escapeHtml(item.filename) + '</div>' +
      '<div class="h-meta">' +
        '<span class="h-conf ' + (item.passed ? 'pass' : 'fail') + '">' + item.confidence + '%</span>' +
        '<span>' + item.timestamp + '</span>' +
      '</div>';
    historyList.appendChild(el);
  }

  // ===== Process File =====
  function processFile(file) {
    if (!file.type || !file.type.startsWith('image/')) {
      showError('Please upload an image (PNG, JPG, GIF, BMP, TIFF, WEBP).');
      return;
    }
    var formData = new FormData();
    formData.append('file', file);
    formData.append('mode', currentMode);
    appendPreprocessParams(formData);
    showLoading();
    fetch('/upload', { method: 'POST', body: formData })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        hideLoading();
        if (data.error) { showError(data.error); return; }
        showResult(data);
        loadHistory();
      })
      .catch(function(err) {
        hideLoading();
        showError('Error: ' + err.message);
      });
  }

  // ===== Process Batch =====
  function processBatch(files) {
    var formData = new FormData();
    for (var i = 0; i < files.length; i++) {
      formData.append('files', files[i]);
    }
    formData.append('mode', currentMode);
    appendPreprocessParams(formData);
    showLoading();
    fetch('/upload_batch', { method: 'POST', body: formData })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        hideLoading();
        if (data.error) { showError(data.error); return; }
        showBatchResults(data);
        loadHistory();
      })
      .catch(function(err) {
        hideLoading();
        showError('Batch error: ' + err.message);
      });
  }

  function showBatchResults(data) {
    if (!resultArea) return;
    resultArea.classList.add('visible');
    var html = '<div class="result-box">';
    html += '<h3>📦 Batch Results (' + data.count + ' images)</h3>';
    html += '<div class="batch-results">';
    data.results.forEach(function(r) {
      var conf = r.confidence || 0;
      var passed = r.passed || false;
      var hasErr = r.error || false;
      var fname = r.filename || 'unknown';
      html += '<div class="batch-card">';
      html += '<div class="b-name">' + escapeHtml(fname) + '</div>';
      if (hasErr) {
        html += '<div class="b-conf" style="color:var(--coral)">Error: ' + escapeHtml(r.error) + '</div>';
      } else {
        html += '<div class="b-conf">Confidence: ' + conf + '%</div>';
        html += '<div class="b-status ' + (passed ? 'pass' : 'fail') + '">' + (passed ? 'PASSED' : 'FAILED') + '</div>';
      }
      html += '</div>';
    });
    html += '</div></div>';
    resultArea.innerHTML = html;
    resultArea.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  // ===== Show Result =====
  function showResult(data) {
    if (!resultArea) return;
    resultArea.classList.add('visible');

    var modeIcon = data.mode === 'ocr' ? '🔤' : (data.mode === 'barcode' ? '📶' : '🎯');
    var modeLabel = data.mode === 'ocr' ? 'OCR Result' : (data.mode === 'barcode' ? 'Barcode / QR Result' : 'Detection Results');
    var passed = data.passed || false;
    var conf = data.confidence || 0;
    var badgeClass = passed ? 'passed' : 'failed';
    var badgeIcon = passed ? '✓' : '✗';

    var html = '<div class="result-box">';
    html += '<h3>' + modeIcon + ' ' + modeLabel + ' <span class="confidence-badge ' + badgeClass + '">' + conf + '% confidence ' + badgeIcon + '</span></h3>';

    // Image Preview
    if (data.original_image && data.processed_image && previewArea) {
      previewArea.classList.add('visible');
      var origImg = document.getElementById('originalImg');
      var compOrig = document.getElementById('comparisonOriginal');
      var compProc = document.getElementById('comparisonProcessed');
      if (origImg) origImg.src = data.original_image;
      if (compOrig) compOrig.src = data.original_image;
      if (compProc) compProc.src = data.processed_image;
      // Wait for both images to load before initializing the slider
      var sliderInited = false;
      var loadedCount = 0;
      function onImgLoad() {
        loadedCount++;
        if (loadedCount >= 2 && !sliderInited) {
          sliderInited = true;
          initComparisonSlider();
        }
      }
      var img1 = document.getElementById('comparisonOriginal');
      var img2 = document.getElementById('comparisonProcessed');
      if (!img1 || !img2) return;
      function onImgError() {
        loadedCount++;
      }
      img1.addEventListener('load', onImgLoad);
      img2.addEventListener('load', onImgLoad);
      img1.addEventListener('error', onImgError);
      img2.addEventListener('error', onImgError);
      // Fallback: if images are already cached, they might not fire load
      if (img1.complete && img1.naturalWidth > 0) loadedCount++;
      if (img2.complete && img2.naturalWidth > 0) loadedCount++;
      if (loadedCount >= 2 && !sliderInited) {
        sliderInited = true;
        setTimeout(initComparisonSlider, 100);
      }
    }

    // OCR Text
    if (data.mode === 'ocr' && data.text) {
      html += '<div class="extracted-text">' + escapeHtml(data.text) + '</div>';

      // Histogram
      if (data.histogram) {
        html += '<div class="histogram">';
        html += '<h5>Confidence Distribution</h5>';
        html += '<div class="histogram-bars">';
        var histValues = Object.keys(data.histogram).map(function(k) { return data.histogram[k]; });
        var maxVal = Math.max(1, ...histValues);
        var colors = ['#22c55e', '#4ade80', '#f59e0b', '#f97316', '#f43f5e'];
        var labels = ['90-100', '80-89', '70-79', '60-69', '<60'];
        var idx = 0;
        for (var key in data.histogram) {
          var val = data.histogram[key];
          var pct = (val / maxVal) * 100;
          html += '<div class="histogram-bar" style="height:' + Math.max(4, pct) + '%;background:' + colors[idx] + '">';
          html += '<span class="h-count">' + val + '</span>';
          html += '<span class="h-label">' + labels[idx] + '%</span>';
          html += '</div>';
          idx++;
        }
        html += '</div></div>';
      }

      // Confidence Details
      if (data.confidence_details && data.confidence_details.length) {
        html += '<div class="conf-details">';
        html += '<h5>Per-Character Confidence</h5>';
        html += '<div class="conf-scroll">';
        data.confidence_details.forEach(function(c) {
          var cls = c.conf >= 90 ? 'high' : (c.conf >= 70 ? 'med' : 'low');
          html += '<span class="conf-chip ' + cls + '">' + escapeHtml(c.text) + ' ' + c.conf + '%</span>';
        });
        html += '</div></div>';
      }
    }

    // Detection
    if (data.mode === 'detection') {
      html += '<p style="margin-bottom:8px;color:var(--gray)">Found <strong>' + data.count + '</strong> object(s).</p>';
      if (data.objects && data.objects.length) {
        html += '<div class="object-list">';
        data.objects.forEach(function(o, i) {
          html += '<div class="object-item">';
          var clsName = o.class || 'Object';
          html += '<div><span class="o-label">' + escapeHtml(clsName) + ' ' + (i+1) + '</span><br><span class="o-bbox">[' + o.bbox.join(', ') + ']</span></div>';
          html += '<span class="o-conf">' + o.confidence + '%</span>';
          html += '</div>';
        });
        html += '</div>';
      }
    }

    // Barcode
    if (data.mode === 'barcode') {
      html += '<p style="margin-bottom:8px;color:var(--gray)">Found <strong>' + data.count + '</strong> barcode(s)/QR code(s).</p>';
      if (data.barcodes && data.barcodes.length) {
        html += '<div class="object-list">';
        data.barcodes.forEach(function(b, i) {
          html += '<div class="object-item">';
          html += '<div><span class="o-label">' + escapeHtml(b.type) + ' ' + (i+1) + '</span><br><span class="o-bbox">' + escapeHtml(b.data) + '</span></div>';
          html += '<span class="o-conf">' + data.confidence + '%</span>';
          html += '</div>';
        });
        html += '</div>';
      }
      if (data.text) {
        html += '<div class="extracted-text">' + escapeHtml(data.text) + '</div>';
      }
    }

    // Validation
    if (data.checks) {
      html += '<div class="validation-list">';
      var checkLabels = {
        'library_integration': 'Library Integration',
        'preprocessing': 'Pre-processing Integrity',
        'accuracy': 'Accuracy Benchmarking (≥80%)',
        'visual_confirmation': 'Visual Confirmation'
      };
      Object.keys(data.checks).forEach(function(key) {
        var ok = data.checks[key];
        html += '<div class="validation-item ' + (ok ? 'pass' : 'fail') + '">';
        html += '<div class="v-icon">' + (ok ? '✓' : '✗') + '</div>';
        html += (checkLabels[key] || key) + '</div>';
      });
      html += '</div>';
    }

    // Actions — use data-* attributes instead of inline onclick to avoid XSS
    html += '<div class="result-actions">';
    if ((data.mode === 'ocr' || data.mode === 'barcode') && data.text) {
      html += '<button class="btn-action primary-action" data-action="downloadText">⬇ Download Text</button>';
      html += '<button class="btn-action" data-action="downloadReport">📄 Export Report</button>';
    }
    if (data.processed_image) {
      html += '<button class="btn-action" data-action="downloadAnnotated">🖼 Download Image</button>';
    }
    html += '<button class="btn-action" data-action="clearResult">✕ Clear</button>';
    html += '</div></div>';

    resultArea.innerHTML = html;
    resultArea.scrollIntoView({ behavior: 'smooth', block: 'start' });

    // Attach event listeners for safe download actions
    var safeText = data.text || '';
    var safeProcessed = data.processed_image || '';
    var safeConf = data.confidence || 0;
    var safeMode = data.mode || 'ocr';
    var safePassed = data.passed || false;

    resultArea.querySelectorAll('[data-action="clearResult"]').forEach(function(btn) {
      btn.addEventListener('click', function() {
        if (resultArea) resultArea.classList.remove('visible');
        if (previewArea) previewArea.classList.remove('visible');
        var rotInp = document.getElementById('rotationInput');
        if (rotInp) rotInp.value = '';
        document.querySelectorAll('.preview-image, .comparison-container img').forEach(function(img) {
          img.style.transform = '';
        });
      });
    });
    resultArea.querySelectorAll('[data-action="downloadText"]').forEach(function(btn) {
      btn.addEventListener('click', function() {
        downloadText(safeText);
      });
    });
    resultArea.querySelectorAll('[data-action="downloadReport"]').forEach(function(btn) {
      btn.addEventListener('click', function() {
        downloadReport(safeText, safeConf, safeMode, safePassed);
      });
    });
    resultArea.querySelectorAll('[data-action="downloadAnnotated"]').forEach(function(btn) {
      btn.addEventListener('click', function() {
        downloadAnnotated(safeProcessed);
      });
    });
  }

  function showError(msg) {
    if (!resultArea) return;
    resultArea.classList.add('visible');
    resultArea.innerHTML =
      '<div class="result-box"><h3 style="color:var(--coral)">⚠ Error</h3><p>' + escapeHtml(msg) + '</p></div>';
  }

  // ===== Helpers =====
  function appendPreprocessParams(fd) {
    fd.append('_csrf_token', getCsrfToken());
    var gsEl = document.getElementById('grayscaleToggle');
    if (gsEl) fd.append('grayscale', gsEl.checked);
    var bkEl = document.getElementById('blurKernel');
    if (bkEl) fd.append('blur_kernel', bkEl.value);
    var tmEl = document.getElementById('thresholdMethod');
    if (tmEl) fd.append('threshold_method', tmEl.value);
    var dsEl = document.getElementById('deskewToggle');
    if (dsEl) fd.append('deskew', dsEl.checked);
    var tbEl = document.getElementById('thresholdBlock');
    if (tbEl) fd.append('threshold_block', tbEl.value);
    var tcEl = document.getElementById('thresholdC');
    if (tcEl) fd.append('threshold_c', tcEl.value);

    var langEl = document.getElementById('ocrLang');
    if (langEl) fd.append('lang', langEl.value);

    var psmEl = document.getElementById('ocrPsm');
    if (psmEl) fd.append('psm', psmEl.value);

    var rotEl = document.getElementById('rotationInput');
    if (rotEl && rotEl.value) fd.append('rotation', rotEl.value);

    var brEl = document.getElementById('brightness');
    if (brEl) fd.append('brightness', brEl.value);

    var crEl = document.getElementById('contrast');
    if (crEl) fd.append('contrast', crEl.value);
  }

  function showLoading() {
    if (loadingOverlay) loadingOverlay.classList.add('visible');
  }

  function hideLoading() {
    if (loadingOverlay) loadingOverlay.classList.remove('visible');
  }

  // ===== Comparison Slider =====
  function initComparisonSlider() {
    var container = document.getElementById('comparisonContainer');
    if (!container) return;
    var overlay = container.querySelector('.comparison-overlay');
    var handle = container.querySelector('.comparison-handle');
    if (!overlay || !handle) return;

    function move(x) {
      var rect = container.getBoundingClientRect();
      var pct = Math.max(0, Math.min(1, (x - rect.left) / rect.width));
      overlay.style.width = (pct * 100) + '%';
      handle.style.left = (pct * 100) + '%';
    }

    function onMove(e) {
      var clientX = e.clientX || (e.touches && e.touches[0].clientX);
      if (clientX) move(clientX);
    }

    container.addEventListener('mousemove', onMove);
    container.addEventListener('touchmove', onMove);
    move(container.getBoundingClientRect().left + container.offsetWidth / 2);
  }
})();

// ===== Dashboard Animations =====
(function() {
  var dashCards = document.querySelectorAll('.dash-card');
  if (!dashCards.length) return;

  function animateValue(el, start, end, suffix, duration) {
    if (!end && end !== 0) return;
    var startTime = null;
    var isPercent = suffix === '%';
    function step(timestamp) {
      if (!startTime) startTime = timestamp;
      var progress = Math.min((timestamp - startTime) / duration, 1);
      var eased = 1 - Math.pow(1 - progress, 3);
      var current = start + (end - start) * eased;
      el.textContent = isPercent ? current.toFixed(1) + '%' : Math.round(current);
      if (progress < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  var observer = new IntersectionObserver(function(entries) {
    entries.forEach(function(entry) {
      if (!entry.isIntersecting) return;
      var card = entry.target;
      var valEl = card.querySelector('.dash-card-value');
      var target = parseFloat(valEl.dataset.value);
      if (isNaN(target)) return;
      var suffix = valEl.dataset.suffix || '';
      animateValue(valEl, 0, target, suffix, 1200);
      observer.unobserve(card);
    });
  }, { threshold: 0.3 });

  dashCards.forEach(function(card) { observer.observe(card); });

  document.querySelectorAll('.dash-donut-ring').forEach(function(circle) {
    var len = circle.getAttribute('stroke-dasharray').split(' ')[0];
    circle.style.strokeDashoffset = len;
    setTimeout(function() {
      circle.style.transition = 'stroke-dashoffset 1.2s cubic-bezier(0.4, 0, 0.2, 1)';
      circle.style.strokeDashoffset = '0';
    }, 200);
  });

  document.querySelectorAll('.dash-bar-fill').forEach(function(bar, i) {
    var w = bar.dataset.width || bar.style.width;
    bar.style.width = '0%';
    setTimeout(function() {
      bar.style.transition = 'width 1s cubic-bezier(0.4, 0, 0.2, 1)';
      bar.style.width = w;
    }, 100 + i * 100);
  });
})();

// ===== Global Download Functions (called from onclick) =====
function downloadText(text) {
  var blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'extracted_text.txt';
  a.click();
  URL.revokeObjectURL(a.href);
}

function downloadAnnotated(b64) {
  fetch('/download_image', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image: b64 })
  })
  .then(function(r) { return r.blob(); })
  .then(function(blob) {
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'annotated_image.png';
    a.click();
    URL.revokeObjectURL(a.href);
  });
}

function downloadReport(text, confidence, mode, passed) {
  fetch('/download_report', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: text, confidence: confidence, mode: mode, passed: passed })
  })
  .then(function(r) { return r.blob(); })
  .then(function(blob) {
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'decodelabs_report.html';
    a.click();
    URL.revokeObjectURL(a.href);
  });
}

// ===== Password Strength Indicator =====
(function() {
  function calcStrength(pw) {
    var score = 0;
    if (pw.length >= 8) score += 25;
    if (pw.length >= 12) score += 15;
    if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) score += 15;
    if (/\d/.test(pw)) score += 15;
    if (/[^a-zA-Z0-9]/.test(pw)) score += 15;
    if (pw.length >= 14) score += 15;
    return Math.min(100, score);
  }

  function getStrengthLabel(score) {
    if (score < 30) return { label: 'Weak', color: '#f43f5e' };
    if (score < 60) return { label: 'Fair', color: '#f59e0b' };
    if (score < 80) return { label: 'Good', color: '#38bdf8' };
    return { label: 'Strong', color: '#4ade80' };
  }

  function bindPasswordInput(inputId, barId, textId) {
    var input = document.getElementById(inputId);
    var bar = document.getElementById(barId);
    var text = document.getElementById(textId);
    if (!input || !bar || !text) return;
    function update() {
      var score = calcStrength(input.value);
      var info = getStrengthLabel(score);
      bar.style.width = score + '%';
      bar.style.background = info.color;
      text.textContent = input.value.length > 0 ? info.label + ' (' + score + '%)' : '';
      text.style.color = info.color;
    }
    input.addEventListener('input', update);
    update();
  }

  bindPasswordInput('password', 'registerPsBar', 'registerPsText');
  bindPasswordInput('new_password', 'changePwPsBar', 'changePwPsText');
})();

// ===== Account Management (Settings) =====
(function() {
  var emailBtn = document.getElementById('updateEmailBtn');
  var emailInput = document.getElementById('emailInput');
  var emailStatus = document.getElementById('emailStatus');

  if (emailBtn && emailInput && emailStatus) {
    emailBtn.addEventListener('click', function() {
      var email = emailInput.value.trim();
      if (!email || !/^[^@]+@[^@]+\.[^@]+$/.test(email)) {
        emailStatus.textContent = 'Please enter a valid email.';
        emailStatus.style.color = 'var(--coral)';
        return;
      }
      fetch('/update_email', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email, _csrf_token: getCsrfToken() })
      })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.error) {
          emailStatus.textContent = 'Error: ' + data.error;
          emailStatus.style.color = 'var(--coral)';
        } else {
          emailStatus.textContent = 'Email updated!';
          emailStatus.style.color = 'var(--mint)';
        }
      })
      .catch(function() {
        emailStatus.textContent = 'Failed to update email.';
        emailStatus.style.color = 'var(--coral)';
      });
    });
  }

  var deleteBtn = document.getElementById('deleteAccountBtn');
  if (deleteBtn) {
    deleteBtn.addEventListener('click', function() {
      if (!confirm('Are you sure you want to permanently delete your account? This cannot be undone.')) return;
      var pw = prompt('Enter your password to confirm deletion:');
      if (!pw) return;
      fetch('/delete_account', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: pw, _csrf_token: getCsrfToken() })
      })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.error) {
          alert('Error: ' + data.error);
        } else {
          alert('Account deleted successfully.');
          window.location.href = '/';
        }
      })
      .catch(function() {
        alert('Failed to delete account.');
      });
    });
  }
})();
