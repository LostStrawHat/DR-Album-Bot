let allPhotos = [];
let selectedIds = new Set();
let isRangeMode = false;
let isAdmin = false;
let videoObserver;
let currentPage = 0;
const photosPerPage = 40;
let isLoading = false;
let hasMore = true;

document.addEventListener("DOMContentLoaded", async () => {
    // Glassmorphism Spotlight Engine
    const filterBar = document.getElementById('filter-bar');
    if (filterBar) {
        filterBar.addEventListener('mousemove', (e) => {
            const rect = filterBar.getBoundingClientRect();
            filterBar.style.setProperty('--mouse-x', `${e.clientX - rect.left}px`);
            filterBar.style.setProperty('--mouse-y', `${e.clientY - rect.top}px`);
        });
        filterBar.addEventListener('mouseleave', () => {
             filterBar.style.setProperty('--mouse-x', `-500px`);
             filterBar.style.setProperty('--mouse-y', `-500px`);
        });
    }

    initVideoObserver();
    await checkAuth();
    await loadPhotos(true); // Initial load (reset)
    await loadAuthors();
    setupEventListeners();
    setupInfiniteScroll();
});

function initVideoObserver() {
    videoObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            const video = entry.target;
            if (entry.isIntersecting) {
                // Video enters the screen
                if (!video.src || video.src === "") {
                    video.src = video.dataset.src;
                }
                video.play().catch(() => {});
            } else {
                // Video leaves the screen
                video.pause();
                // We keep the src so it doesn't flicker if scrolled back quickly,
                // but we pause to save CPU/Battery.
            }
        });
    }, {
        threshold: 0.5 // Trigger when at least 50% visible
    });
}

async function checkAuth() {
    try {
        const resp = await fetch('/api/auth/status');
        const data = await resp.json();
        isAdmin = data.is_admin;
        updateAdminUI();
    } catch (e) {}
}

function updateAdminUI() {
    const adminElements = document.querySelectorAll('.admin-only');
    const loginBtn = document.getElementById('admin-login-btn');
    
    adminElements.forEach(el => {
        el.style.display = isAdmin ? 'flex' : 'none';
    });
    
    if (loginBtn) {
        loginBtn.style.display = isAdmin ? 'none' : 'flex';
    }
}

async function loadPhotos(reset = false) {
    if (isLoading || (!hasMore && !reset)) return;
    
    isLoading = true;
    if (reset) {
        currentPage = 0;
        allPhotos = [];
        hasMore = true;
        const gallery = document.getElementById('gallery');
        if (gallery) gallery.innerHTML = '<div class="loading-spinner"></div>';
    }

    try {
        const offset = currentPage * photosPerPage;
        const req = await fetch(`/api/photos?limit=${photosPerPage}&offset=${offset}`);
        const newPhotos = await req.json();
        
        if (newPhotos.length < photosPerPage) {
            hasMore = false;
        }
        
        allPhotos = [...allPhotos, ...newPhotos];
        renderGallery();
        currentPage++;
    } catch (e) {
        console.error("Failed to fetch photos", e);
    } finally {
        isLoading = false;
    }
}

async function loadAuthors() {
    try {
        const req = await fetch('/api/authors');
        const authors = await req.json();
        const select = document.getElementById('author-filter');
        // Keep only the first option (All Senders)
        select.innerHTML = '<option value="all">All Senders</option>';
        authors.forEach(author => {
            const opt = document.createElement('option');
            opt.value = author.id;
            opt.textContent = author.name;
            select.appendChild(opt);
        });
    } catch (e) {}
}

// Dates removed since we use range date-pickers now

function toLocalDateString(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

function renderGallery() {
    const gallery = document.getElementById('gallery');
    gallery.innerHTML = '';
    
    // For infinite scroll, we re-render the full allPhotos list (filtered).
    // This ensures client-side filters continue to work correctly as more data arrives.
    
    const authorFilter = document.getElementById('author-filter').value;
    const typeFilter = document.getElementById('type-filter').value;
    const startDate = document.getElementById('start-date').value;
    const endDate = document.getElementById('end-date').value;
    
    const filtered = allPhotos.filter(p => {
        let authorMatch = authorFilter === 'all' || String(p.user_id) === String(authorFilter);
        let typeMatch = typeFilter === 'all' || 
                        (typeFilter === 'image' && !p.is_video) || 
                        (typeFilter === 'video' && p.is_video);
        
        let dateMatch = true;
        if (p.sent_timestamp) {
            const pStr = toLocalDateString(new Date(p.sent_timestamp));
            if (isRangeMode) {
                if (startDate && pStr < startDate) dateMatch = false;
                if (endDate && pStr > endDate) dateMatch = false;
            } else {
                // In single-day mode, we match exactly if a date is picked
                if (startDate && pStr !== startDate) dateMatch = false;
            }
        }
        
        return authorMatch && typeMatch && dateMatch;
    });

    if (filtered.length === 0) {
        gallery.innerHTML = '<p style="text-align:center; width:100%; color:#94a3b8; font-size:1.2rem;">No magic moments found.</p>';
        return;
    }

    filtered.forEach(p => {
        const card = document.createElement('div');
        card.className = `media-card ${selectedIds.has(p.id) ? 'selected' : ''}`;
        card.dataset.id = p.id;
        
        const check = document.createElement('div');
        check.className = 'check-indicator';
        
        let media;
        if (p.is_video) {
            media = document.createElement('video');
            // Optimization: Don't set src immediately for grid videos to save bandwidth.
            // Only set src and play on hover.
            media.dataset.src = p.proxy_url;
            media.poster = `/thumbnail/${p.id}`;
            media.muted = true;
            media.loop = true;
            media.preload = "none"; 
            media.playsInline = true;
            
            media.setAttribute('muted', '');
            media.setAttribute('loop', '');
            media.setAttribute('playsinline', '');

            // Observe for scroll-to-play
            videoObserver.observe(media);
        } else {
            media = document.createElement('img');
            media.src = `/thumbnail/${p.id}`;
            media.loading = "lazy";
        }
        
        media.style.cursor = "zoom-in";

        const footer = document.createElement('div');
        footer.className = 'card-footer';
        
        // Convert UTC to Local time for display
        let localDateStr = "Unknown";
        if (p.sent_timestamp) {
            const d = new Date(p.sent_timestamp);
            localDateStr = d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
        }

        footer.innerHTML = `<p>By ${p.user_name}</p><p style="opacity:0.6">${localDateStr}</p>`;

        card.appendChild(media);
        card.appendChild(check);
        
        if (p.discord_url) {
            const discordBtn = document.createElement('a');
            discordBtn.className = 'discord-jump-btn';
            discordBtn.href = p.discord_url;
            discordBtn.target = '_blank';
            discordBtn.innerHTML = `<svg viewBox="0 0 127.14 96.36" width="16" height="16" fill="currentColor"><path d="M107.7,8.07A105.15,105.15,0,0,0,81.47,0a72.06,72.06,0,0,0-3.36,6.83A97.68,97.68,0,0,0,49,6.83,72.06,72.06,0,0,0,45.64,0,105.89,105.89,0,0,0,19.39,8.09C2.71,32.65-1.82,56.6.48,80.21a105.73,105.73,0,0,0,32.22,16.15,77.7,77.7,0,0,0,7.37-12,67.65,67.65,0,0,1-10.51-5c.87-.64,1.74-1.31,2.57-2a78.58,78.58,0,0,0,63.56,0c.84.69,1.7,1.36,2.56,2a67.59,67.59,0,0,1-10.51,5,77.66,77.66,0,0,0,7.37,12,105.27,105.27,0,0,0,32.25-16.15C130,51,123.63,27.15,107.7,8.07ZM42.45,65.69C36.18,65.69,31,60,31,53s5-12.74,11.43-12.74S54,46,53.89,53,48.84,65.69,42.45,65.69Zm42.24,0C78.41,65.69,73.25,60,73.25,53s5-12.74,11.44-12.74S96.23,46,96.12,53,91.08,65.69,84.69,65.69Z"/></svg>`;
            discordBtn.title = 'View original message in Discord';
            discordBtn.addEventListener('click', (e) => e.stopPropagation());
            card.appendChild(discordBtn);
        }

        // Add Copy Link Button
        const copyBtn = document.createElement('button');
        copyBtn.className = 'copy-link-btn';
        copyBtn.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path></svg>';
        copyBtn.title = 'Copy direct media link';
        copyBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            copyToClipboard(p.proxy_url);
        });
        card.appendChild(copyBtn);

        card.appendChild(footer);
        
        card.addEventListener('click', (e) => {
            // Priority 1: Do nothing if action buttons were clicked (they have stopPropagation)
            if (e.target.closest('.discord-jump-btn') || e.target.closest('.copy-link-btn')) return;

            // Priority 2: If we click the checkmark or footer, Always Toggle Select
            if (e.target.closest('.check-indicator') || e.target.closest('.card-footer')) {
                toggleSelect(p.id, card);
                return;
            }

            // Priority 3: For the media/image part:
            // If already in selection mode (at least 1 item is selected), clicking media also selects.
            // If NOT in selection mode, clicking media opens Lightbox.
            if (selectedIds.size > 0) {
                toggleSelect(p.id, card);
            } else {
                openLightbox(p.proxy_url, p.is_video, p.discord_url);
            }
        });
        gallery.appendChild(card);
    });
}

function copyToClipboard(text) {
    // Ensure relative paths become absolute URLs for sharing
    let fullUrl = text;
    if (text.startsWith('/')) {
        fullUrl = window.location.origin + text;
    }
    
    navigator.clipboard.writeText(fullUrl).then(() => {
        showToast("Link copied to clipboard!");
    }).catch(err => {
        console.error('Failed to copy: ', err);
    });
}

function showToast(message) {
    const toast = document.createElement('div');
    toast.className = 'toast-notification';
    toast.innerText = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.classList.add('show'), 100);
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function toggleSelect(id, cardElement) {
    if (selectedIds.has(id)) {
        selectedIds.delete(id);
        cardElement.classList.remove('selected');
    } else {
        selectedIds.add(id);
        cardElement.classList.add('selected');
    }
    updateActionButtons();
}

function updateActionButtons() {
    const downloadBtn = document.getElementById('download-bulk');
    const deleteBtn = document.getElementById('delete-selected-btn');
    
    const count = selectedIds.size;
    downloadBtn.querySelector('span').textContent = count > 0 ? `Download ${count}` : "Download";
    downloadBtn.disabled = count === 0;
    
    if (deleteBtn) {
        deleteBtn.querySelector('span').textContent = count > 0 ? `Delete ${count}` : "Delete";
        deleteBtn.disabled = count === 0;
    }
}

function setupEventListeners() {
    // Mobile Filter Toggle
    const mobileFilterBtn = document.getElementById('mobile-filter-btn');
    const filterGroupBubble = document.getElementById('filter-group-bubble');

    if (mobileFilterBtn && filterGroupBubble) {
        mobileFilterBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            filterGroupBubble.classList.toggle('active');
        });

        document.addEventListener('click', (e) => {
            if (!filterGroupBubble.contains(e.target) && !mobileFilterBtn.contains(e.target)) {
                filterGroupBubble.classList.remove('active');
            }
        });
        
        filterGroupBubble.addEventListener('click', (e) => {
            e.stopPropagation();
        });
    }

    document.getElementById('author-filter').addEventListener('change', () => loadPhotos(true));
    document.getElementById('type-filter').addEventListener('change', () => loadPhotos(true));
    document.getElementById('start-date').addEventListener('change', () => loadPhotos(true));
    document.getElementById('end-date').addEventListener('change', () => loadPhotos(true));
    
    document.getElementById('range-toggle').addEventListener('click', () => {
        isRangeMode = !isRangeMode;
        document.getElementById('end-date-group').classList.toggle('active', isRangeMode);
        loadPhotos(true);
    });

    document.getElementById('clear-filters').addEventListener('click', () => {
        document.getElementById('author-filter').value = 'all';
        document.getElementById('type-filter').value = 'all';
        document.getElementById('start-date').value = '';
        document.getElementById('end-date').value = '';
        loadPhotos(true);
    });

    document.getElementById('lightbox-close').addEventListener('click', closeLightbox);
    document.getElementById('lightbox').addEventListener('click', (e) => {
        if (e.target.id === 'lightbox') closeLightbox();
    });
    
    document.getElementById('select-all').addEventListener('click', () => {
        const visibleCards = document.querySelectorAll('.media-card');
        if (selectedIds.size === visibleCards.length && visibleCards.length > 0) {
            selectedIds.clear();
        } else {
            visibleCards.forEach(c => selectedIds.add(c.dataset.id));
        }
        updateActionButtons();
        // We don't call renderGallery here to avoid flickering, just update the classes
        visibleCards.forEach(c => {
            if (selectedIds.has(c.dataset.id)) {
                c.classList.add('selected');
            } else {
                c.classList.remove('selected');
            }
        });
    });

    // Auth Listeners
    document.getElementById('admin-login-btn').addEventListener('click', () => {
        document.getElementById('login-modal').classList.add('active');
    });
    document.getElementById('close-login').addEventListener('click', () => {
        document.getElementById('login-modal').classList.remove('active');
    });
    document.getElementById('submit-login').addEventListener('click', async () => {
        const password = document.getElementById('admin-password').value;
        const resp = await fetch('/api/auth/login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ password })
        });
        const data = await resp.json();
        if (data.success) {
            isAdmin = true;
            updateAdminUI();
            document.getElementById('login-modal').classList.remove('active');
            document.getElementById('admin-password').value = '';
        } else {
            alert("Invalid Password");
        }
    });

    document.getElementById('admin-logout-btn').addEventListener('click', async () => {
        await fetch('/api/auth/logout', {method: 'POST'});
        isAdmin = false;
        updateAdminUI();
    });

    document.getElementById('delete-selected-btn').addEventListener('click', async () => {
        const count = selectedIds.size;
        if (count === 0) return;
        if (!confirm(`Are you sure you want to PERMANENTLY delete ${count} item(s)?`)) return;

        const resp = await fetch('/api/delete', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ ids: Array.from(selectedIds) })
        });
        const data = await resp.json();
        if (data.success) {
            selectedIds.clear();
            updateActionButtons();
            await loadPhotos(true);
            await loadAuthors();
        } else {
            alert("Failed to delete items.");
        }
    });

    document.getElementById('download-bulk').addEventListener('click', async () => {
        if (selectedIds.size === 0) return;
        
        const btn = document.getElementById('download-bulk');
        const span = btn.querySelector('span');
        const originalText = span.textContent;
        span.textContent = "Zipping... ⏳";
        btn.disabled = true;

        try {
            const req = await fetch('/api/download_bulk', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message_ids: Array.from(selectedIds) })
            });
            
            if (req.ok) {
                const blob = await req.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.style.display = 'none';
                a.href = url;
                a.download = 'Vault_Archive.zip';
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
            } else {
                alert("Failed to create ZIP.");
            }
        } catch (e) {
            console.error(e);
            alert("Error downloading!");
        }

        span.textContent = originalText;
        btn.disabled = false;
    });
}

function openLightbox(url, isVideo, discordUrl = null) {
    const lightbox = document.getElementById('lightbox');
    
    // Clear old visual inside lightbox
    let oldContent = lightbox.querySelector('.lightbox-content');
    if (oldContent) oldContent.remove();
    let oldDiscordBtn = lightbox.querySelector('.lightbox-discord-btn');
    if (oldDiscordBtn) oldDiscordBtn.remove();
    let oldCopyBtn = lightbox.querySelector('.lightbox-copy-btn');
    if (oldCopyBtn) oldCopyBtn.remove();
    
    let content;
    if (isVideo) {
        content = document.createElement('video');
        content.src = url;
        content.controls = true;
        content.autoplay = true;
        content.playsInline = true;
        content.setAttribute('playsinline', '');
        content.className = 'lightbox-content';
    } else {
        content = document.createElement('img');
        content.src = url;
        content.className = 'lightbox-content';
    }
    
    lightbox.appendChild(content);

    if (discordUrl) {
        const discordBtn = document.createElement('a');
        discordBtn.className = 'lightbox-discord-btn';
        discordBtn.href = discordUrl;
        discordBtn.target = '_blank';
        discordBtn.innerHTML = `<svg viewBox="0 0 127.14 96.36" width="24" height="24" fill="currentColor"><path d="M107.7,8.07A105.15,105.15,0,0,0,81.47,0a72.06,72.06,0,0,0-3.36,6.83A97.68,97.68,0,0,0,49,6.83,72.06,72.06,0,0,0,45.64,0,105.89,105.89,0,0,0,19.39,8.09C2.71,32.65-1.82,56.6.48,80.21a105.73,105.73,0,0,0,32.22,16.15,77.7,77.7,0,0,0,7.37-12,67.65,67.65,0,0,1-10.51-5c.87-.64,1.74-1.31,2.57-2a78.58,78.58,0,0,0,63.56,0c.84.69,1.7,1.36,2.56,2a67.59,67.59,0,0,1-10.51,5,77.66,77.66,0,0,0,7.37,12,105.27,105.27,0,0,0,32.25-16.15C130,51,123.63,27.15,107.7,8.07ZM42.45,65.69C36.18,65.69,31,60,31,53s5-12.74,11.43-12.74S54,46,53.89,53,48.84,65.69,42.45,65.69Zm42.24,0C78.41,65.69,73.25,60,73.25,53s5-12.74,11.44-12.74S96.23,46,96.12,53,91.08,65.69,84.69,65.69Z"/></svg>`;
        discordBtn.title = 'View inside Discord';
        lightbox.appendChild(discordBtn);
    }

    const copyBtn = document.createElement('button');
    copyBtn.className = 'lightbox-copy-btn';
    copyBtn.innerHTML = '<svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path></svg>';
    copyBtn.title = 'Copy direct link';
    copyBtn.onclick = (e) => {
        e.stopPropagation();
        copyToClipboard(url);
    };
    lightbox.appendChild(copyBtn);

    lightbox.classList.add('active');
}

function closeLightbox() {
    const lightbox = document.getElementById('lightbox');
    lightbox.classList.remove('active');
    
    // Stop video and audio abruptly to prevent phantom sound
    const video = lightbox.querySelector('video');
    if (video) video.pause();
}

function setupInfiniteScroll() {
    window.addEventListener('scroll', () => {
        if (window.innerHeight + window.scrollY >= document.body.offsetHeight - 500) {
            loadPhotos();
        }
    });
}

