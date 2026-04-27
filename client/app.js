/**
 * NexusChat — Client-Side Application
 * 
 * Handles:
 * - Authentication (login/register)
 * - WebSocket connection management with auto-reconnect
 * - Real-time message rendering
 * - Room management (create, join, switch)
 * - Typing indicators
 * - Presence tracking
 * - Message history pagination
 */

// ==============================================
// Configuration
// ==============================================
const CONFIG = {
    // API base URL — adjust based on deployment
    API_BASE: window.location.origin + '/api/v1',
    // WebSocket URL
    WS_BASE: (window.location.protocol === 'https:' ? 'wss://' : 'ws://') + window.location.host,
    // Reconnection settings
    RECONNECT_BASE_DELAY: 1000,
    RECONNECT_MAX_DELAY: 30000,
    // Typing indicator debounce (ms)
    TYPING_DEBOUNCE: 2000,
    // Messages per page
    MESSAGES_PER_PAGE: 50,
};

// ==============================================
// State
// ==============================================
const state = {
    accessToken: null,
    refreshToken: null,
    user: null,
    ws: null,
    currentRoom: null,
    rooms: [],
    onlineUsers: {},    // room_id -> [user objects]
    typingUsers: {},    // room_id -> {user_id: username}
    reconnectAttempts: 0,
    reconnectTimer: null,
    typingTimer: null,
    isTyping: false,
    messageCursors: {},  // room_id -> next_cursor
    messageCache: {},    // room_id -> [messages]
    lastSenders: {},     // room_id -> last sender_id (for grouping)
};

// ==============================================
// DOM Elements
// ==============================================
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const dom = {
    // Screens
    authScreen: $('#auth-screen'),
    chatScreen: $('#chat-screen'),
    // Auth
    loginForm: $('#login-form'),
    registerForm: $('#register-form'),
    loginUsername: $('#login-username'),
    loginPassword: $('#login-password'),
    registerUsername: $('#register-username'),
    registerEmail: $('#register-email'),
    registerPassword: $('#register-password'),
    registerDisplay: $('#register-display'),
    loginBtn: $('#login-btn'),
    registerBtn: $('#register-btn'),
    authError: $('#auth-error'),
    showRegister: $('#show-register'),
    showLogin: $('#show-login'),
    // Sidebar
    sidebar: $('#sidebar'),
    userAvatar: $('#user-avatar'),
    userDisplayName: $('#user-display-name'),
    roomList: $('#room-list'),
    createRoomBtn: $('#create-room-btn'),
    browseRoomsBtn: $('#browse-rooms-btn'),
    logoutBtn: $('#logout-btn'),
    connectionStatus: $('#connection-status'),
    sidebarToggle: $('#sidebar-toggle'),
    // Chat
    noRoomView: $('#no-room-view'),
    chatView: $('#chat-view'),
    chatRoomName: $('#chat-room-name'),
    chatRoomMembers: $('#chat-room-members'),
    messagesContainer: $('#messages-container'),
    messages: $('#messages'),
    messageInput: $('#message-input'),
    sendBtn: $('#send-btn'),
    typingIndicator: $('#typing-indicator'),
    typingUsers: $('#typing-users'),
    loadMoreBtn: $('#load-more-btn'),
    loadMoreMessages: $('#load-more-messages'),
    leaveRoomBtn: $('#leave-room-btn'),
    // Members
    toggleMembersBtn: $('#toggle-members-btn'),
    closeMembersBtn: $('#close-members-btn'),
    membersPanel: $('#members-panel'),
    onlineMembers: $('#online-members'),
    offlineMembers: $('#offline-members'),
    onlineCount: $('#online-count'),
    // Modals
    createRoomModal: $('#create-room-modal'),
    createRoomForm: $('#create-room-form'),
    roomNameInput: $('#room-name-input'),
    roomDescInput: $('#room-desc-input'),
    roomPrivateInput: $('#room-private-input'),
    browseRoomsModal: $('#browse-rooms-modal'),
    browseRoomsList: $('#browse-rooms-list'),
    // Toast
    toastContainer: $('#toast-container'),
};

// ==============================================
// API Client
// ==============================================
async function api(method, path, body = null, auth = true) {
    const headers = { 'Content-Type': 'application/json' };
    if (auth && state.accessToken) {
        headers['Authorization'] = `Bearer ${state.accessToken}`;
    }

    const opts = { method, headers };
    if (body) opts.body = JSON.stringify(body);

    const res = await fetch(`${CONFIG.API_BASE}${path}`, opts);

    if (res.status === 401 && auth) {
        // Try token refresh
        const refreshed = await refreshToken();
        if (refreshed) {
            headers['Authorization'] = `Bearer ${state.accessToken}`;
            const retryRes = await fetch(`${CONFIG.API_BASE}${path}`, { method, headers, body: opts.body });
            if (!retryRes.ok) throw await parseError(retryRes);
            return retryRes.json();
        }
        logout();
        throw new Error('Session expired');
    }

    if (!res.ok) throw await parseError(res);
    
    // Handle 204 No Content
    const text = await res.text();
    return text ? JSON.parse(text) : {};
}

async function parseError(res) {
    try {
        const data = await res.json();
        return new Error(data.detail || 'Request failed');
    } catch {
        return new Error(`HTTP ${res.status}`);
    }
}

async function refreshToken() {
    if (!state.refreshToken) return false;
    try {
        const res = await fetch(`${CONFIG.API_BASE}/auth/refresh`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh_token: state.refreshToken }),
        });
        if (!res.ok) return false;
        const data = await res.json();
        state.accessToken = data.access_token;
        state.refreshToken = data.refresh_token;
        saveTokens();
        return true;
    } catch {
        return false;
    }
}

// ==============================================
// Token Management
// ==============================================
function saveTokens() {
    localStorage.setItem('chat_access_token', state.accessToken);
    localStorage.setItem('chat_refresh_token', state.refreshToken);
}

function loadTokens() {
    state.accessToken = localStorage.getItem('chat_access_token');
    state.refreshToken = localStorage.getItem('chat_refresh_token');
}

function clearTokens() {
    state.accessToken = null;
    state.refreshToken = null;
    localStorage.removeItem('chat_access_token');
    localStorage.removeItem('chat_refresh_token');
}

// ==============================================
// Authentication
// ==============================================
async function login(username, password) {
    const data = await api('POST', '/auth/login', { username, password }, false);
    state.accessToken = data.access_token;
    state.refreshToken = data.refresh_token;
    saveTokens();
    await loadUserProfile();
    showChatScreen();
    connectWebSocket();
    await loadRooms();
}

async function register(username, email, password, displayName) {
    await api('POST', '/auth/register', {
        username, email, password, display_name: displayName || username,
    }, false);
    // Auto-login after registration
    await login(username, password);
}

async function loadUserProfile() {
    state.user = await api('GET', '/auth/me');
    dom.userDisplayName.textContent = state.user.display_name || state.user.username;
    dom.userAvatar.textContent = (state.user.username || 'U')[0].toUpperCase();
}

function logout() {
    clearTokens();
    state.user = null;
    state.currentRoom = null;
    state.rooms = [];
    if (state.ws) {
        state.ws.close();
        state.ws = null;
    }
    showAuthScreen();
}

// ==============================================
// Screen Management
// ==============================================
function showAuthScreen() {
    dom.authScreen.classList.add('active');
    dom.chatScreen.classList.remove('active');
}

function showChatScreen() {
    dom.authScreen.classList.remove('active');
    dom.chatScreen.classList.add('active');
}

// ==============================================
// WebSocket Connection
// ==============================================
function connectWebSocket() {
    if (state.ws && state.ws.readyState <= 1) return;

    const wsUrl = `${CONFIG.WS_BASE}/ws/chat?token=${state.accessToken}`;
    updateConnectionStatus('connecting');

    const ws = new WebSocket(wsUrl);
    state.ws = ws;

    ws.onopen = () => {
        state.reconnectAttempts = 0;
        updateConnectionStatus('connected');
        showToast('Connected to chat server', 'success');

        // Re-join rooms
        if (state.currentRoom) {
            wsSend('join_room', { room_id: state.currentRoom.id });
        }
    };

    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            handleWSMessage(data);
        } catch (e) {
            console.error('Failed to parse WS message:', e);
        }
    };

    ws.onclose = (event) => {
        updateConnectionStatus('disconnected');
        if (event.code !== 1000) {
            scheduleReconnect();
        }
    };

    ws.onerror = () => {
        updateConnectionStatus('disconnected');
    };
}

function wsSend(event, data = {}) {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify({ event, data }));
    }
}

function scheduleReconnect() {
    if (state.reconnectTimer) return;

    const delay = Math.min(
        CONFIG.RECONNECT_BASE_DELAY * Math.pow(2, state.reconnectAttempts),
        CONFIG.RECONNECT_MAX_DELAY
    );
    state.reconnectAttempts++;

    updateConnectionStatus('connecting', `Reconnecting in ${Math.round(delay / 1000)}s...`);

    state.reconnectTimer = setTimeout(() => {
        state.reconnectTimer = null;
        connectWebSocket();
    }, delay);
}

function updateConnectionStatus(status, text = null) {
    dom.connectionStatus.className = `connection-status ${status}`;
    const statusText = dom.connectionStatus.querySelector('.status-text');

    if (text) {
        statusText.textContent = text;
    } else {
        const labels = { connected: 'Connected', connecting: 'Connecting...', disconnected: 'Disconnected' };
        statusText.textContent = labels[status] || status;
    }
}

// ==============================================
// WebSocket Message Handlers
// ==============================================
function handleWSMessage(data) {
    const { event, data: payload } = data;

    switch (event) {
        case 'message':
            handleIncomingMessage(payload);
            break;
        case 'presence':
            handlePresenceUpdate(payload);
            break;
        case 'typing':
            handleTypingIndicator(payload);
            break;
        case 'online_users':
            handleOnlineUsers(payload);
            break;
        case 'system':
            handleSystemMessage(payload);
            break;
        case 'pong':
            // Heartbeat response — no action needed
            break;
        case 'ping':
            wsSend('pong');
            break;
        case 'error':
            showToast(payload.detail || 'An error occurred', 'error');
            break;
        default:
            console.log('Unknown WS event:', event, payload);
    }
}

function handleIncomingMessage(payload) {
    const roomId = payload.room_id;

    // Cache the message
    if (!state.messageCache[roomId]) state.messageCache[roomId] = [];
    state.messageCache[roomId].push(payload);

    // Render if in current room
    if (state.currentRoom && state.currentRoom.id === roomId) {
        renderMessage(payload);
        scrollToBottom();
    }
}

function handlePresenceUpdate(payload) {
    const { room_id, user_id, username, status } = payload;

    if (!state.onlineUsers[room_id]) state.onlineUsers[room_id] = [];

    if (status === 'online') {
        const exists = state.onlineUsers[room_id].find(u => u.user_id === user_id);
        if (!exists) {
            state.onlineUsers[room_id].push({ user_id, username });
        }
    } else {
        state.onlineUsers[room_id] = state.onlineUsers[room_id].filter(u => u.user_id !== user_id);
    }

    if (state.currentRoom && state.currentRoom.id === room_id) {
        updateMembersPanel();
    }
}

function handleOnlineUsers(payload) {
    const { room_id, users } = payload;
    state.onlineUsers[room_id] = users || [];

    if (state.currentRoom && state.currentRoom.id === room_id) {
        updateMembersPanel();
    }
}

function handleTypingIndicator(payload) {
    const { room_id, user_id, username, is_typing } = payload;

    if (user_id === state.user?.id) return;

    if (!state.typingUsers[room_id]) state.typingUsers[room_id] = {};

    if (is_typing) {
        state.typingUsers[room_id][user_id] = username;
    } else {
        delete state.typingUsers[room_id][user_id];
    }

    if (state.currentRoom && state.currentRoom.id === room_id) {
        updateTypingIndicator();
    }
}

function handleSystemMessage(payload) {
    if (state.currentRoom && state.currentRoom.id === (payload.room_id || '')) {
        renderSystemMessage(payload.content);
        scrollToBottom();
    }
}

// ==============================================
// Room Management
// ==============================================
async function loadRooms() {
    try {
        const data = await api('GET', '/rooms?my_rooms=true');
        state.rooms = data.rooms || [];
        renderRoomList();
    } catch (e) {
        console.error('Failed to load rooms:', e);
    }
}

function renderRoomList() {
    if (state.rooms.length === 0) {
        dom.roomList.innerHTML = `
            <div class="room-list-empty">
                <p>No rooms yet</p>
                <p class="subtle">Create or join a room to start chatting</p>
            </div>`;
        return;
    }

    const roomColors = ['#6C63FF', '#00D2FF', '#8B5CF6', '#F59E0B', '#22C55E', '#EF4444', '#EC4899'];

    dom.roomList.innerHTML = state.rooms.map((room, i) => {
        const color = roomColors[i % roomColors.length];
        const initial = room.name[0].toUpperCase();
        const isActive = state.currentRoom?.id === room.id;
        return `
            <div class="room-item ${isActive ? 'active' : ''}" 
                 data-room-id="${room.id}" 
                 onclick="switchRoom('${room.id}')">
                <div class="room-icon" style="background: ${color}20; color: ${color}">
                    ${initial}
                </div>
                <div class="room-info">
                    <div class="room-name">${escapeHtml(room.name)}</div>
                    <div class="room-preview">${room.member_count || 0} members</div>
                </div>
            </div>`;
    }).join('');
}

async function switchRoom(roomId) {
    // Leave current room
    if (state.currentRoom) {
        wsSend('leave_room', { room_id: state.currentRoom.id });
    }

    // Find room data
    const room = state.rooms.find(r => r.id === roomId);
    if (!room) return;

    state.currentRoom = room;

    // Update UI
    dom.noRoomView.classList.remove('active');
    dom.chatView.classList.add('active');
    dom.chatRoomName.textContent = room.name;
    dom.chatRoomMembers.textContent = `${room.member_count || 0} members`;
    dom.messages.innerHTML = '';
    state.lastSenders = {};

    // Highlight active room
    $$('.room-item').forEach(el => {
        el.classList.toggle('active', el.dataset.roomId === roomId);
    });

    // Close sidebar on mobile
    dom.sidebar.classList.remove('open');

    // Join room on WebSocket
    wsSend('join_room', { room_id: roomId });

    // Load message history
    await loadMessages(roomId);
}

async function loadMessages(roomId, before = null) {
    try {
        const params = new URLSearchParams({ limit: CONFIG.MESSAGES_PER_PAGE });
        if (before) params.set('before', before);

        const data = await api('GET', `/rooms/${roomId}/messages?${params}`);

        // Show/hide load more button
        dom.loadMoreMessages.style.display = data.has_more ? 'block' : 'none';
        state.messageCursors[roomId] = data.next_cursor;

        // Render messages
        if (!before) {
            dom.messages.innerHTML = '';
            state.lastSenders[roomId] = null;
        }

        data.messages.forEach(msg => renderMessage(msg, !!before));

        if (!before) scrollToBottom();
    } catch (e) {
        console.error('Failed to load messages:', e);
    }
}

async function createRoom(name, description, isPrivate) {
    try {
        const room = await api('POST', '/rooms', { name, description, is_private: isPrivate });
        showToast(`Room "${name}" created!`, 'success');
        closeModal('create-room-modal');
        await loadRooms();
        switchRoom(room.id);
    } catch (e) {
        showToast(e.message || 'Failed to create room', 'error');
    }
}

async function joinRoom(roomId) {
    try {
        await api('POST', `/rooms/${roomId}/join`);
        showToast('Joined room!', 'success');
        closeModal('browse-rooms-modal');
        await loadRooms();
        switchRoom(roomId);
    } catch (e) {
        showToast(e.message || 'Failed to join room', 'error');
    }
}

async function leaveCurrentRoom() {
    if (!state.currentRoom) return;
    try {
        wsSend('leave_room', { room_id: state.currentRoom.id });
        await api('DELETE', `/rooms/${state.currentRoom.id}/leave`);
        showToast('Left the room', 'info');
        state.currentRoom = null;
        dom.chatView.classList.remove('active');
        dom.noRoomView.classList.add('active');
        await loadRooms();
    } catch (e) {
        showToast(e.message || 'Failed to leave room', 'error');
    }
}

async function browseRooms() {
    openModal('browse-rooms-modal');
    dom.browseRoomsList.innerHTML = '<div class="loading-state">Loading rooms...</div>';

    try {
        const data = await api('GET', '/rooms');
        const rooms = data.rooms || [];

        if (rooms.length === 0) {
            dom.browseRoomsList.innerHTML = '<div class="loading-state">No rooms available. Create one!</div>';
            return;
        }

        const joinedIds = new Set(state.rooms.map(r => r.id));

        dom.browseRoomsList.innerHTML = rooms.map(room => {
            const isJoined = joinedIds.has(room.id);
            return `
                <div class="browse-room-item">
                    <div class="browse-room-info">
                        <h4>${escapeHtml(room.name)}</h4>
                        <p>${escapeHtml(room.description || 'No description')} · ${room.member_count || 0} members</p>
                    </div>
                    ${isJoined
                        ? '<button class="btn btn-ghost btn-small" disabled>Joined</button>'
                        : `<button class="btn btn-primary btn-small" onclick="joinRoom('${room.id}')">Join</button>`
                    }
                </div>`;
        }).join('');
    } catch (e) {
        dom.browseRoomsList.innerHTML = `<div class="loading-state">Error: ${e.message}</div>`;
    }
}

// ==============================================
// Message Rendering
// ==============================================
function renderMessage(msg, prepend = false) {
    const isOwn = msg.sender_id === state.user?.id;
    const isSystem = msg.message_type === 'system';
    const roomId = msg.room_id;

    if (isSystem) {
        renderSystemMessage(msg.content);
        return;
    }

    // Check for message grouping
    const lastSender = state.lastSenders[roomId];
    const isGrouped = lastSender === msg.sender_id;
    state.lastSenders[roomId] = msg.sender_id;

    const time = formatTime(msg.created_at);
    const initial = (msg.sender_username || '?')[0].toUpperCase();

    const messageEl = document.createElement('div');
    messageEl.className = `message ${isOwn ? 'own' : ''} ${isGrouped ? 'grouped' : ''}`;
    messageEl.dataset.messageId = msg.id;

    messageEl.innerHTML = `
        <div class="message-avatar">${initial}</div>
        <div class="message-content">
            <div class="message-header">
                <span class="message-sender">${escapeHtml(msg.sender_username || 'Unknown')}</span>
                <span class="message-time">${time}</span>
            </div>
            <div class="message-text">${escapeHtml(msg.content)}</div>
        </div>`;

    if (prepend) {
        dom.messages.prepend(messageEl);
    } else {
        dom.messages.appendChild(messageEl);
    }
}

function renderSystemMessage(content) {
    const messageEl = document.createElement('div');
    messageEl.className = 'message system';
    messageEl.innerHTML = `<div class="message-text">${escapeHtml(content)}</div>`;
    dom.messages.appendChild(messageEl);
}

function scrollToBottom() {
    requestAnimationFrame(() => {
        dom.messagesContainer.scrollTop = dom.messagesContainer.scrollHeight;
    });
}

// ==============================================
// Typing Indicator
// ==============================================
function handleTyping() {
    if (!state.currentRoom) return;

    if (!state.isTyping) {
        state.isTyping = true;
        wsSend('typing_start', { room_id: state.currentRoom.id });
    }

    clearTimeout(state.typingTimer);
    state.typingTimer = setTimeout(() => {
        state.isTyping = false;
        wsSend('typing_stop', { room_id: state.currentRoom.id });
    }, CONFIG.TYPING_DEBOUNCE);
}

function updateTypingIndicator() {
    if (!state.currentRoom) return;

    const roomTyping = state.typingUsers[state.currentRoom.id] || {};
    const names = Object.values(roomTyping);

    if (names.length === 0) {
        dom.typingIndicator.style.display = 'none';
        return;
    }

    dom.typingIndicator.style.display = 'flex';

    if (names.length === 1) {
        dom.typingUsers.textContent = `${names[0]} is typing...`;
    } else if (names.length === 2) {
        dom.typingUsers.textContent = `${names[0]} and ${names[1]} are typing...`;
    } else {
        dom.typingUsers.textContent = `${names.length} people are typing...`;
    }
}

// ==============================================
// Members Panel
// ==============================================
function updateMembersPanel() {
    if (!state.currentRoom) return;

    const onlineList = state.onlineUsers[state.currentRoom.id] || [];
    dom.onlineCount.textContent = onlineList.length;

    dom.onlineMembers.innerHTML = onlineList.map(user => `
        <div class="member-item">
            <div class="member-avatar">
                ${(user.username || '?')[0].toUpperCase()}
                <span class="presence-dot online"></span>
            </div>
            <span class="member-name">${escapeHtml(user.username || 'Unknown')}</span>
        </div>
    `).join('') || '<div class="loading-state" style="padding:8px;font-size:0.82rem">No one online</div>';
}

function toggleMembersPanel() {
    dom.membersPanel.classList.toggle('active');
}

// ==============================================
// Modals
// ==============================================
function openModal(id) {
    document.getElementById(id).classList.add('active');
}

function closeModal(id) {
    document.getElementById(id).classList.remove('active');
}

// ==============================================
// Toast Notifications
// ==============================================
function showToast(message, type = 'info', duration = 4000) {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;

    dom.toastContainer.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('toast-dismiss');
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// ==============================================
// Utilities
// ==============================================
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatTime(isoString) {
    const date = new Date(isoString);
    const now = new Date();
    const isToday = date.toDateString() === now.toDateString();

    if (isToday) {
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    if (date.toDateString() === yesterday.toDateString()) {
        return 'Yesterday ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    return date.toLocaleDateString([], { month: 'short', day: 'numeric' }) +
        ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function generateUUID() {
    return crypto.randomUUID ? crypto.randomUUID() :
        'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
            const r = Math.random() * 16 | 0;
            return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
        });
}

// ==============================================
// Event Listeners
// ==============================================
function initEventListeners() {
    // --- Auth ---
    dom.loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        dom.loginBtn.classList.add('loading');
        dom.authError.textContent = '';
        try {
            await login(dom.loginUsername.value, dom.loginPassword.value);
        } catch (err) {
            dom.authError.textContent = err.message;
        } finally {
            dom.loginBtn.classList.remove('loading');
        }
    });

    dom.registerForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        dom.registerBtn.classList.add('loading');
        dom.authError.textContent = '';
        try {
            await register(
                dom.registerUsername.value,
                dom.registerEmail.value,
                dom.registerPassword.value,
                dom.registerDisplay.value,
            );
        } catch (err) {
            dom.authError.textContent = err.message;
        } finally {
            dom.registerBtn.classList.remove('loading');
        }
    });

    dom.showRegister.addEventListener('click', (e) => {
        e.preventDefault();
        dom.loginForm.classList.remove('active');
        dom.registerForm.classList.add('active');
        dom.authError.textContent = '';
    });

    dom.showLogin.addEventListener('click', (e) => {
        e.preventDefault();
        dom.registerForm.classList.remove('active');
        dom.loginForm.classList.add('active');
        dom.authError.textContent = '';
    });

    dom.logoutBtn.addEventListener('click', logout);

    // --- Rooms ---
    dom.createRoomBtn.addEventListener('click', () => openModal('create-room-modal'));
    dom.browseRoomsBtn.addEventListener('click', browseRooms);

    dom.createRoomForm.addEventListener('submit', (e) => {
        e.preventDefault();
        createRoom(
            dom.roomNameInput.value,
            dom.roomDescInput.value,
            dom.roomPrivateInput.checked,
        );
    });

    dom.leaveRoomBtn.addEventListener('click', leaveCurrentRoom);

    // --- Messages ---
    dom.messageInput.addEventListener('input', () => {
        // Auto-resize textarea
        dom.messageInput.style.height = 'auto';
        dom.messageInput.style.height = Math.min(dom.messageInput.scrollHeight, 120) + 'px';

        // Enable/disable send button
        dom.sendBtn.disabled = !dom.messageInput.value.trim();

        // Typing indicator
        handleTyping();
    });

    dom.messageInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    dom.sendBtn.addEventListener('click', sendMessage);

    dom.loadMoreBtn.addEventListener('click', () => {
        if (state.currentRoom) {
            const cursor = state.messageCursors[state.currentRoom.id];
            if (cursor) loadMessages(state.currentRoom.id, cursor);
        }
    });

    // --- Members Panel ---
    dom.toggleMembersBtn.addEventListener('click', toggleMembersPanel);
    dom.closeMembersBtn.addEventListener('click', () => dom.membersPanel.classList.remove('active'));

    // --- Sidebar Toggle (Mobile) ---
    dom.sidebarToggle.addEventListener('click', () => dom.sidebar.classList.toggle('open'));

    // --- Modal Close ---
    $$('.close-modal').forEach(btn => {
        btn.addEventListener('click', () => {
            closeModal(btn.dataset.modal);
        });
    });

    // Close modal on overlay click
    $$('.modal-overlay').forEach(overlay => {
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                overlay.classList.remove('active');
            }
        });
    });
}

function sendMessage() {
    const content = dom.messageInput.value.trim();
    if (!content || !state.currentRoom) return;

    const idempotencyKey = generateUUID();

    wsSend('message', {
        room_id: state.currentRoom.id,
        content: content,
        idempotency_key: idempotencyKey,
    });

    // Clear input
    dom.messageInput.value = '';
    dom.messageInput.style.height = 'auto';
    dom.sendBtn.disabled = true;

    // Stop typing
    if (state.isTyping) {
        state.isTyping = false;
        clearTimeout(state.typingTimer);
        wsSend('typing_stop', { room_id: state.currentRoom.id });
    }
}

// ==============================================
// Initialization
// ==============================================
async function init() {
    initEventListeners();
    loadTokens();

    if (state.accessToken) {
        try {
            await loadUserProfile();
            showChatScreen();
            connectWebSocket();
            await loadRooms();
        } catch (e) {
            // Token expired or invalid
            clearTokens();
            showAuthScreen();
        }
    } else {
        showAuthScreen();
    }
}

// Make functions available globally for inline onclick handlers
window.switchRoom = switchRoom;
window.joinRoom = joinRoom;

// Start the app
document.addEventListener('DOMContentLoaded', init);
