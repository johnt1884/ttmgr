// ==UserScript==
// @name         Numbered TikTok video links under each container
// @namespace    your.namespace
// @version      1.2
// @description  Adds numbered clickable video links below TikTok video containers
// @match        *://*.tiktok.com/*
// @grant        none
// ==/UserScript==

(function() {
    'use strict';

    function addNumberedVideoLinks() {
        const containers = document.querySelectorAll('div[id^="column-item-video-container-"]');

        containers.forEach((container, index) => {
            // Avoid duplicates
            if (container.querySelector('.video-link-marker')) return;

            // Find the first <a> link inside
            const linkEl = container.querySelector('a[href]');
            if (!linkEl) return;

            const videoUrl = linkEl.href;

            // Create clickable link element
            const linkDiv = document.createElement('div');
            linkDiv.className = 'video-link-marker';
            linkDiv.style.marginTop = '5px';
            linkDiv.style.fontSize = '12px';
            linkDiv.style.wordBreak = 'break-all';
            linkDiv.style.color = '#0af';

            const anchor = document.createElement('a');
            anchor.href = videoUrl;
            anchor.target = '_blank';
            anchor.textContent = `${index + 1}. ${videoUrl}`;
            anchor.style.color = '#0af';
            anchor.style.textDecoration = 'none';

            linkDiv.appendChild(anchor);
            container.appendChild(linkDiv);
        });
    }

    // Run initially
    addNumberedVideoLinks();

    // Re-run automatically when new posts load (TikTok loads content dynamically)
    const observer = new MutationObserver(() => addNumberedVideoLinks());
    observer.observe(document.body, { childList: true, subtree: true });
})();
