let allPhotos = [];
let selectedIds = new Set();
let isRangeMode = false;
let isAdmin = false;

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

    await checkAuth();
    await loadPhotos();
    await loadAuthors();
    setupEventListeners();
});

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

async function loadPhotos() {
    try {
        const req = await fetch('/api/photos');
        allPhotos = await req.json();
        renderGallery();
    } catch (e) {
        console.error("Failed to fetch photos", e);
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
            media.src = p.proxy_url;
            media.muted = true;
            media.loop = true;
            card.addEventListener('mouseenter', () => media.play());
            card.addEventListener('mouseleave', () => media.pause());
        } else {
            media = document.createElement('img');
            media.src = p.proxy_url;
            media.loading = "lazy";
        }
        
        media.style.cursor = "zoom-in";
        media.addEventListener('click', (e) => {
            e.stopPropagation();
            openLightbox(p.proxy_url, p.is_video);
        });

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
        card.appendChild(footer);
        
        card.addEventListener('click', () => toggleSelect(p.id, card));
        gallery.appendChild(card);
    });
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

    document.getElementById('author-filter').addEventListener('change', renderGallery);
    document.getElementById('type-filter').addEventListener('change', renderGallery);
    document.getElementById('start-date').addEventListener('change', renderGallery);
    document.getElementById('end-date').addEventListener('change', renderGallery);
    
    document.getElementById('range-toggle').addEventListener('click', () => {
        isRangeMode = !isRangeMode;
        document.getElementById('end-date-group').classList.toggle('active', isRangeMode);
        document.getElementById('range-toggle').querySelector('span').textContent = isRangeMode ? "Single Day" : "Range";
        renderGallery();
    });

    document.getElementById('clear-filters').addEventListener('click', () => {
        document.getElementById('author-filter').value = 'all';
        document.getElementById('type-filter').value = 'all';
        document.getElementById('start-date').value = '';
        document.getElementById('end-date').value = '';
        renderGallery();
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
        renderGallery();
        updateActionButtons();
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

    // Management Listeners
    document.getElementById('add-photo-btn').addEventListener('click', () => {
        document.getElementById('add-photo-modal').classList.add('active');
    });
    document.getElementById('close-add').addEventListener('click', () => {
        document.getElementById('add-photo-modal').classList.remove('active');
    });
    document.getElementById('submit-add').addEventListener('click', async () => {
        const userId = document.getElementById('add-user-id').value;
        const url = document.getElementById('add-url').value;
        const fileName = document.getElementById('add-filename').value;
        
        if (!userId || !url) return alert("User ID and URL are required");

        const resp = await fetch('/api/admin/add', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ user_id: userId, url, file_name: fileName, timestamp: new Date().toISOString() })
        });
        const data = await resp.json();
        if (data.success) {
            document.getElementById('add-photo-modal').classList.remove('active');
            // Clear inputs
            document.getElementById('add-user-id').value = '';
            document.getElementById('add-url').value = '';
            document.getElementById('add-filename').value = '';
            await loadPhotos();
            await loadAuthors();
        } else {
            alert("Failed to add photo: " + data.error);
        }
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
            await loadPhotos();
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

function openLightbox(url, isVideo) {
    const lightbox = document.getElementById('lightbox');
    
    // Clear old visual inside lightbox
    let oldContent = lightbox.querySelector('.lightbox-content');
    if (oldContent) oldContent.remove();
    
    let content;
    if (isVideo) {
        content = document.createElement('video');
        content.src = url;
        content.controls = true;
        content.autoplay = true;
        content.className = 'lightbox-content';
    } else {
        content = document.createElement('img');
        content.src = url;
        content.className = 'lightbox-content';
    }
    
    lightbox.appendChild(content);
    lightbox.classList.add('active');
}

function closeLightbox() {
    const lightbox = document.getElementById('lightbox');
    lightbox.classList.remove('active');
    
    // Stop video and audio abruptly to prevent phantom sound
    const video = lightbox.querySelector('video');
    if (video) video.pause();
}

