/*
	Eventually by HTML5 UP
	html5up.net | @ajlkn
	Free for personal and commercial use under the CCA 3.0 license (html5up.net/license)
*/

(function() {

	"use strict";

	var	$body = document.querySelector('body');

	// Methods/polyfills.

		// classList | (c) @remy | github.com/remy/polyfills | rem.mit-license.org
			!function(){function t(t){this.el=t;for(var n=t.className.replace(/^\s+|\s+$/g,"").split(/\s+/),i=0;i<n.length;i++)e.call(this,n[i])}function n(t,n,i){Object.defineProperty?Object.defineProperty(t,n,{get:i}):t.__defineGetter__(n,i)}if(!("undefined"==typeof window.Element||"classList"in document.documentElement)){var i=Array.prototype,e=i.push,s=i.splice,o=i.join;t.prototype={add:function(t){this.contains(t)||(e.call(this,t),this.el.className=this.toString())},contains:function(t){return-1!=this.el.className.indexOf(t)},item:function(t){return this[t]||null},remove:function(t){if(this.contains(t)){for(var n=0;n<this.length&&this[n]!=t;n++);s.call(this,n,1),this.el.className=this.toString()}},toString:function(){return o.call(this," ")},toggle:function(t){return this.contains(t)?this.remove(t):this.add(t),this.contains(t)}},window.DOMTokenList=t,n(Element.prototype,"classList",function(){return new t(this)})}}();

		// canUse
			window.canUse=function(p){if(!window._canUse)window._canUse=document.createElement("div");var e=window._canUse.style,up=p.charAt(0).toUpperCase()+p.slice(1);return p in e||"Moz"+up in e||"Webkit"+up in e||"O"+up in e||"ms"+up in e};

		// window.addEventListener
			(function(){if("addEventListener"in window)return;window.addEventListener=function(type,f){window.attachEvent("on"+type,f)}})();

	// Play initial animations on page load.
		window.addEventListener('load', function() {
			window.setTimeout(function() {
				$body.classList.remove('is-preload');
			}, 100);
		});

	// Slideshow Background.
		(function() {

			// Settings.
				var settings = {

					// Images (in the format of 'url': 'alignment').
						images: {
							'/static/images/bg01.jpg': 'center',
							'/static/images/bg02.jpg': 'center',
							'/static/images/bg03.jpg': 'center'
						},

					// Delay.
						delay: 6000

				};

			// Vars.
				var	pos = 0, lastPos = 0,
					$wrapper, $bgs = [], $bg,
					k, v;

			// Create BG wrapper, BGs.
				$wrapper = document.createElement('div');
					$wrapper.id = 'bg';
					$body.appendChild($wrapper);

				for (k in settings.images) {

					// Create BG.
						$bg = document.createElement('div');
							$bg.style.backgroundImage = 'url("' + k + '")';
							$bg.style.backgroundPosition = settings.images[k];
							$wrapper.appendChild($bg);

					// Add it to array.
						$bgs.push($bg);

				}

			// Main loop.
				$bgs[pos].classList.add('visible');
				$bgs[pos].classList.add('top');

				// Bail if we only have a single BG or the client doesn't support transitions.
					if ($bgs.length == 1
					||	!canUse('transition'))
						return;

				window.setInterval(function() {

					lastPos = pos;
					pos++;

					// Wrap to beginning if necessary.
						if (pos >= $bgs.length)
							pos = 0;

					// Swap top images.
						$bgs[lastPos].classList.remove('top');
						$bgs[pos].classList.add('visible');
						$bgs[pos].classList.add('top');

					// Hide last image after a short delay.
						window.setTimeout(function() {
							$bgs[lastPos].classList.remove('visible');
						}, settings.delay / 2);

				}, settings.delay);

		})();

	// Generic button integration: clicking a visible button opens the corresponding hidden file chooser and auto-uploads
		(function() {
			// Find all elements that end with '-button'
			var buttons = document.querySelectorAll('[id$="-button"]');

			Array.prototype.forEach.call(buttons, function(button) {
				// Derive base name: e.g., 'courses-button' -> 'courses'
				var id = button.id;
				var base = id.replace(/-button$/, '');
				var fileInput = document.getElementById(base + '-file');
				var form = document.getElementById(base + '-form');

				if (!fileInput || !form) return;

				button.addEventListener('click', function() { 
					console.log('[upload] button click, base=', base, 'form=', form && form.id, 'action=', form && form.action);
					fileInput.click(); 
				});

				fileInput.addEventListener('change', function() {
					if (fileInput.files && fileInput.files.length > 0) {
						console.log('[upload] file selected for base=', base, 'filename=', fileInput.files[0].name);
						var evt = new Event('submit', { bubbles: true, cancelable: true });
						form.dispatchEvent(evt);
					}
				});
			});

		})();


	// Generate Button handler (replaces signup form behavior)
			(function() {
				var gen = document.getElementById('generate-button');
				if (!gen) return;

				// Attach a message span reusing the same styles.
				var message = document.createElement('span');
				message.classList.add('message');
				gen.parentElement.appendChild(message);

				message._show = function(type, text) {
					message.innerHTML = text;
					message.classList.add(type);
					message.classList.add('visible');
					window.setTimeout(function() { message._hide(); }, 3000);
				};

				message._hide = function() { message.classList.remove('visible'); };

				gen.addEventListener('click', function() {
					message._show('success', 'Generating...');
					fetch('/generate', { method: 'POST' })
					.then(function(res) {
						if (!res.ok) return res.json().then(function(j){ throw new Error(j.message || 'Generate failed'); });
						return res.blob();
					}).then(function(blob) {
						// Trigger download
						var url = window.URL.createObjectURL(blob);
						var a = document.createElement('a');
						a.href = url;
						a.download = 'timetable.xlsx';
						document.body.appendChild(a);
						a.click();
						a.remove();
						window.URL.revokeObjectURL(url);
						message._show('success', 'Downloaded');
					}).catch(function(err) {
						console.error('[generate] error', err);
						message._show('failure', err.message || 'Failed');
					});
				});

			})();

		// Upload forms handling.
			(function() {

				var uploadForms = document.querySelectorAll('.upload-form');

				if (!uploadForms) return;

				Array.prototype.forEach.call(uploadForms, function(form) {

					// Append a message span to each form (same pattern as signup form)
					var message = document.createElement('span');
					message.classList.add('message');
					form.appendChild(message);

					message._show = function(type, text) {
						message.innerHTML = text;
						message.classList.add(type);
						message.classList.add('visible');
						window.setTimeout(function() { message._hide(); }, 3000);
					};
					message._hide = function() { message.classList.remove('visible'); };

					form.addEventListener('submit', function(e) {
						e.preventDefault();
						var submit = form.querySelector('input[type=submit], input[type=button], button');
						var fileInput = form.querySelector('input[type=file]');
						if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
							message._show('failure', 'Please select a file.');
							return;
						}

						if (submit) submit.disabled = true;
						console.log('[upload] starting upload ->', form.action, fileInput.files[0] && fileInput.files[0].name);
						var fd = new FormData();
						fd.append('file', fileInput.files[0]);
						// Instruct server to save the uploaded file using the target name (e.g., 'instructors.csv')
						var baseId = form.id.replace(/-form$/, '');
						fd.append('use_target_name', 'true');

						fetch(form.action, {
							method: 'POST',
							body: fd
						}).then(function(res) {
							if (!res.ok) throw new Error('Upload failed');
							return res.json();
						}).then(function(json) {
							console.log('[upload] server json ->', json);
							if (submit) submit.disabled = false;
							if (json.success) {
								fileInput.value = '';
								message._show('success', json.message || 'Uploaded');
							} else {
								message._show('failure', json.message || 'Upload failed');
							}
						}).catch(function(err) {
							console.error('[upload] error ->', err);
							if (submit) submit.disabled = false;
							message._show('failure', err.message || 'Upload failed');
						});
					});

				});

			})();

})();