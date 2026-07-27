/* ==========================================================
   FXGuard AI — account, consent and cloud-history client
   ========================================================== */
'use strict';

(() => {
  const configuredApi = String(window.FXGUARD_API_URL ?? '').trim();
  const API = configuredApi || window.location.origin;

  const state = {
    config: {
      enabled: false,
      methods: [],
      registration_enabled: false,
      account_deletion_enabled: false,
      terms_version: '1.0',
      privacy_version: '1.0',
    },
    user: null,
    checks: [],
    csrfToken: '',
    intent: 'signin',
    channel: 'phone',
    pendingContact: '',
    pendingAccepted: false,
  };

  const byId = id => document.getElementById(id);
  const setHidden = (id, hidden) => byId(id)?.classList.toggle('hidden', hidden);

  async function requestJson(path, options = {}) {
    const headers = { ...(options.headers || {}) };
    if (options.body && !headers['Content-Type']) headers['Content-Type'] = 'application/json';
    if (options.csrf) headers['X-CSRF-Token'] = state.csrfToken;

    let response;
    try {
      response = await fetch(`${API}${path}`, {
        method: options.method || 'GET',
        credentials: 'include',
        headers,
        body: options.body,
      });
    } catch (error) {
      throw new Error('Cannot connect to the account service. Please try again.');
    }

    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(payload.detail || 'The account request could not be completed.');
      error.status = response.status;
      throw error;
    }
    if (payload.csrf_token) state.csrfToken = payload.csrf_token;
    return payload;
  }

  function normalisePhone() {
    const prefix = byId('authCountryCode')?.value || '+250';
    const entered = String(byId('authPhone')?.value || '').trim();
    if (entered.startsWith('+')) return entered.replace(/[\s()-]/g, '');
    const digits = entered.replace(/\D/g, '').replace(/^0+/, '');
    return `${prefix}${digits}`;
  }

  function currentContact() {
    return state.channel === 'email'
      ? String(byId('authEmail')?.value || '').trim().toLowerCase()
      : normalisePhone();
  }

  function setError(id, message = '') {
    const element = byId(id);
    if (!element) return;
    element.textContent = message;
    element.classList.toggle('hidden', !message);
  }

  function setButtonLoading(id, loading) {
    const button = byId(id);
    if (!button) return;
    button.disabled = loading;
    button.classList.toggle('loading', loading);
  }

  function closeModal(id) {
    byId(id)?.classList.add('hidden');
  }

  function openModal(id) {
    byId(id)?.classList.remove('hidden');
  }

  function showAuthStage(stage) {
    setHidden('authContactStage', stage !== 'contact');
    setHidden('authCodeStage', stage !== 'code');
    setHidden('migrationStage', stage !== 'migration');
  }

  function showMigrationStage() {
    const localChecks = window.FXGuardApp?.getLocalChecks() || [];
    if (byId('authModalKicker')) byId('authModalKicker').textContent = 'Your account';
    if (byId('authModalTitle')) byId('authModalTitle').textContent = 'Save device checks';
    if (byId('migrationMessage')) {
      byId('migrationMessage').textContent = `${localChecks.length} guest ${localChecks.length === 1 ? 'check is' : 'checks are'} still only in this browser. Add ${localChecks.length === 1 ? 'it' : 'them'} to your account?`;
    }
    showAuthStage('migration');
  }

  function availableChannels() {
    return Array.isArray(state.config.methods)
      ? state.config.methods.filter(method => method === 'email' || method === 'phone')
      : [];
  }

  function applyAccountCapabilities() {
    const methods = availableChannels();
    document.querySelectorAll('[data-auth-channel]').forEach(button => {
      button.classList.toggle('hidden', !methods.includes(button.dataset.authChannel));
    });
    setHidden('authMethodTabs', methods.length < 2);
    setHidden('accountDangerZone', !state.config.account_deletion_enabled);
    setHidden('accountDeletionUnavailable', Boolean(state.config.account_deletion_enabled));
    if (methods.length && !methods.includes(state.channel)) setChannel(methods[0]);
  }

  function setChannel(channel) {
    if (!availableChannels().includes(channel)) return;
    state.channel = channel;
    document.querySelectorAll('[data-auth-channel]').forEach(button => {
      const active = button.dataset.authChannel === channel;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', String(active));
    });
    setHidden('authPhoneGroup', channel !== 'phone');
    setHidden('authEmailGroup', channel !== 'email');
    setError('authContactError');
  }

  function authCopy() {
    const signingUp = state.intent === 'signup';
    if (byId('authModalKicker')) byId('authModalKicker').textContent = signingUp ? 'New account' : 'Welcome back';
    if (byId('authModalTitle')) byId('authModalTitle').textContent = signingUp ? 'Create account' : 'Sign in';
    if (byId('authIntro')) {
      const methods = availableChannels();
      const destination = methods.length === 1
        ? `${methods[0] === 'email' ? 'your email address' : 'your phone number'}`
        : 'where to receive a one-time code';
      byId('authIntro').textContent = signingUp
        ? `Enter ${destination}. No password is needed.`
        : methods.length === 1
          ? `Use ${destination} connected to your account.`
          : 'Use the phone number or email connected to your account.';
    }
    setHidden('legalAcceptance', !signingUp);
    const legalCheckbox = byId('acceptLegal');
    if (legalCheckbox) {
      legalCheckbox.checked = false;
      legalCheckbox.required = signingUp;
      legalCheckbox.setAttribute('aria-invalid', 'false');
    }
    byId('legalAcceptance')?.classList.remove('has-error');
    if (byId('authSwitchCopy')) {
      setHidden('authSwitchCopy', !signingUp);
      byId('authSwitchCopy').innerHTML = signingUp
        ? 'Already have an account? <button type="button" data-switch-auth="signin">Sign in</button>'
        : '';
    }
  }

  function openAuth(intent = 'signin') {
    state.intent = intent;
    state.pendingContact = '';
    state.pendingAccepted = false;
    const methods = availableChannels();
    authCopy();
    if (methods.length) setChannel(methods[0]);
    showAuthStage('contact');
    setError('authContactError');
    setError('authCodeError');
    if (byId('authPhone')) byId('authPhone').value = '';
    if (byId('authEmail')) byId('authEmail').value = '';
    if (byId('authCode')) byId('authCode').value = '';
    const available = state.config.enabled && methods.length > 0;
    if (byId('authUnavailableMessage')) {
      byId('authUnavailableMessage').textContent = state.config.message
        || 'You can continue using payment checks as a guest.';
    }
    setHidden('authUnavailable', available);
    setHidden('authContactStage', !available);
    openModal('authModal');
    window.setTimeout(() => {
      if (!available) return;
      (state.channel === 'phone' ? byId('authPhone') : byId('authEmail'))?.focus();
    }, 50);
  }

  function updateUI() {
    const signedIn = Boolean(state.user);
    setHidden('guestAccountActions', signedIn);
    setHidden('accountButton', !signedIn);
    if (state.user) {
      if (byId('accountIdentifier')) byId('accountIdentifier').textContent = state.user.identifier;
      if (byId('accountSettingsIdentifier')) byId('accountSettingsIdentifier').textContent = state.user.identifier;
    }

    const resultVisible = !byId('resultContent')?.classList.contains('hidden');
    setHidden(
      'saveAccountPrompt',
      signedIn || !state.config.registration_enabled || !resultVisible,
    );
    applyAccountCapabilities();

    const localCount = window.FXGuardApp?.getLocalChecks().length || 0;
    const importButton = byId('accountImportButton');
    if (importButton) {
      importButton.disabled = localCount === 0;
      importButton.textContent = localCount ? `Save ${localCount} to account` : 'Nothing to save';
    }
  }

  async function loadChecks() {
    if (!state.user) return;
    try {
      const payload = await requestJson('/api/checks');
      state.checks = Array.isArray(payload.checks) ? payload.checks : [];
      window.FXGuardApp?.renderRecentChecks();
    } catch (error) {
      if (error.status === 401) {
        state.user = null;
        state.checks = [];
        updateUI();
        window.FXGuardApp?.renderRecentChecks();
      } else {
        window.FXGuardApp?.toast(error.message, 'error');
      }
    }
  }

  async function restoreSession() {
    try {
      state.config = await requestJson('/api/auth/config');
      applyAccountCapabilities();
      const session = await requestJson('/api/auth/session');
      if (session.authenticated) {
        state.user = session.user;
        state.csrfToken = session.csrf_token || '';
        await loadChecks();
      }
    } catch (error) {
      console.info('Account service is unavailable:', error);
    } finally {
      updateUI();
    }
  }

  async function startOtp(event) {
    event.preventDefault();
    setError('authContactError');
    const contact = currentContact();
    const accepted = Boolean(byId('acceptLegal')?.checked);

    if (state.intent === 'signup' && !accepted) {
      const legalCheckbox = byId('acceptLegal');
      byId('legalAcceptance')?.classList.add('has-error');
      legalCheckbox?.setAttribute('aria-invalid', 'true');
      setError('authContactError', 'Agree to the Terms of Use and acknowledge the Privacy Notice to continue.');
      legalCheckbox?.focus();
      return;
    }
    if (!contact) {
      setError('authContactError', `Enter your ${state.channel === 'phone' ? 'phone number' : 'email address'}.`);
      return;
    }

    setButtonLoading('sendCodeButton', true);
    try {
      const payload = {
        channel: state.channel,
        contact,
        intent: state.intent,
        accepted_terms: accepted,
        terms_version: state.config.terms_version,
        privacy_version: state.config.privacy_version,
      };
      const result = await requestJson('/api/auth/otp/start', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      state.pendingContact = contact;
      state.pendingAccepted = accepted;
      if (byId('codeSentMessage')) byId('codeSentMessage').textContent = result.message || 'Enter the code we sent you.';
      showAuthStage('code');
      window.setTimeout(() => byId('authCode')?.focus(), 50);
    } catch (error) {
      setError('authContactError', error.message);
    } finally {
      setButtonLoading('sendCodeButton', false);
    }
  }

  async function verifyOtp(event) {
    event.preventDefault();
    setError('authCodeError');
    const token = String(byId('authCode')?.value || '').replace(/\s/g, '');
    if (token.length < 4) {
      setError('authCodeError', 'Enter the code sent to you.');
      return;
    }

    setButtonLoading('verifyCodeButton', true);
    try {
      const payload = await requestJson('/api/auth/otp/verify', {
        method: 'POST',
        body: JSON.stringify({
          channel: state.channel,
          contact: state.pendingContact,
          token,
          intent: state.intent,
          accepted_terms: state.pendingAccepted,
          terms_version: state.config.terms_version,
          privacy_version: state.config.privacy_version,
        }),
      });
      state.user = payload.user;
      state.csrfToken = payload.csrf_token || '';
      await loadChecks();
      updateUI();

      const localChecks = window.FXGuardApp?.getLocalChecks() || [];
      if (localChecks.length) {
        showMigrationStage();
      } else {
        closeModal('authModal');
        window.FXGuardApp?.toast('You are signed in.', 'success');
      }
    } catch (error) {
      setError('authCodeError', error.message);
    } finally {
      setButtonLoading('verifyCodeButton', false);
    }
  }

  async function saveCheck(entry, { silent = false } = {}) {
    if (!state.user) throw new Error('Sign in to save this result.');
    const payload = await requestJson('/api/checks', {
      method: 'POST',
      csrf: true,
      body: JSON.stringify({ checked_at: entry.checkedAt, result: entry.full }),
    });
    const saved = payload.check;
    const signature = window.FXGuardApp?.checkSignature(saved);
    state.checks = [
      saved,
      ...state.checks.filter(check => window.FXGuardApp?.checkSignature(check) !== signature),
    ];
    window.FXGuardApp?.renderRecentChecks();
    if (!silent) window.FXGuardApp?.toast('Result saved to your account.', 'success');
    return saved;
  }

  async function importLocalChecks() {
    const localChecks = window.FXGuardApp?.getLocalChecks() || [];
    if (!localChecks.length) {
      closeModal('authModal');
      closeModal('accountModal');
      return;
    }
    setButtonLoading('importLocalChecksButton', true);
    if (byId('accountImportButton')) byId('accountImportButton').disabled = true;
    try {
      for (const check of [...localChecks].reverse()) {
        if (check.full) await saveCheck(check, { silent: true });
      }
      window.FXGuardApp?.clearLocalChecks();
      await loadChecks();
      closeModal('authModal');
      closeModal('accountModal');
      window.FXGuardApp?.toast('Checks from this device were saved to your account.', 'success');
    } catch (error) {
      window.FXGuardApp?.toast(error.message, 'error');
    } finally {
      setButtonLoading('importLocalChecksButton', false);
      updateUI();
    }
  }

  async function deleteCheck(checkId) {
    if (!state.user || !checkId) return;
    if (!window.confirm('Delete this saved check? This cannot be undone.')) return;
    try {
      await requestJson(`/api/checks/${encodeURIComponent(checkId)}`, {
        method: 'DELETE',
        csrf: true,
      });
      state.checks = state.checks.filter(check => check.id !== checkId);
      window.FXGuardApp?.renderRecentChecks();
      window.FXGuardApp?.toast('Saved check deleted.');
    } catch (error) {
      window.FXGuardApp?.toast(error.message, 'error');
    }
  }

  async function clearChecks() {
    if (!state.user) return;
    if (!state.checks.length) return;
    if (!window.confirm('Clear all checks saved in your account? This cannot be undone.')) return;
    try {
      await requestJson('/api/checks', { method: 'DELETE', csrf: true });
      state.checks = [];
      window.FXGuardApp?.renderRecentChecks();
      window.FXGuardApp?.toast('Saved checks cleared.');
    } catch (error) {
      window.FXGuardApp?.toast(error.message, 'error');
    }
  }

  function openAccount() {
    if (!state.user) return openAuth('signin');
    setHidden('deleteAccountConfirm', true);
    if (byId('deleteAccountInput')) byId('deleteAccountInput').value = '';
    if (byId('deleteAccountButton')) byId('deleteAccountButton').disabled = true;
    updateUI();
    openModal('accountModal');
  }

  async function signOut() {
    try {
      await requestJson('/api/auth/logout', { method: 'POST', csrf: true });
    } catch (error) {
      window.FXGuardApp?.toast(error.message, 'error');
      return;
    }
    state.user = null;
    state.checks = [];
    state.csrfToken = '';
    closeModal('accountModal');
    updateUI();
    window.FXGuardApp?.renderRecentChecks();
    window.FXGuardApp?.toast('You are signed out.');
  }

  async function exportAccount() {
    try {
      const payload = await requestJson('/api/account/export');
      delete payload.csrf_token;
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `fxguard-account-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 2000);
      window.FXGuardApp?.toast('Your account information was downloaded.', 'success');
    } catch (error) {
      window.FXGuardApp?.toast(error.message, 'error');
    }
  }

  async function deleteAccount() {
    if (byId('deleteAccountInput')?.value !== 'DELETE') return;
    const button = byId('deleteAccountButton');
    if (button) button.disabled = true;
    try {
      await requestJson('/api/account', { method: 'DELETE', csrf: true });
      state.user = null;
      state.checks = [];
      state.csrfToken = '';
      closeModal('accountModal');
      updateUI();
      window.FXGuardApp?.renderRecentChecks();
      window.FXGuardApp?.toast('Your account and cloud-saved checks were deleted.', 'success');
    } catch (error) {
      window.FXGuardApp?.toast(error.message, 'error');
      if (button) button.disabled = false;
    }
  }

  function bindEvents() {
    byId('signInButton')?.addEventListener('click', () => openAuth('signin'));
    byId('resultSignUpButton')?.addEventListener('click', () => openAuth('signup'));
    byId('accountButton')?.addEventListener('click', openAccount);
    byId('authModalClose')?.addEventListener('click', () => closeModal('authModal'));
    byId('accountModalClose')?.addEventListener('click', () => closeModal('accountModal'));
    byId('authContactForm')?.addEventListener('submit', startOtp);
    byId('acceptLegal')?.addEventListener('change', event => {
      if (!event.target.checked) return;
      const acceptance = byId('legalAcceptance');
      if (acceptance?.classList.contains('has-error')) {
        acceptance.classList.remove('has-error');
        event.target.setAttribute('aria-invalid', 'false');
        setError('authContactError');
      }
    });
    byId('authCodeForm')?.addEventListener('submit', verifyOtp);
    byId('changeContactButton')?.addEventListener('click', () => showAuthStage('contact'));
    byId('importLocalChecksButton')?.addEventListener('click', importLocalChecks);
    byId('skipMigrationButton')?.addEventListener('click', () => {
      closeModal('authModal');
      window.FXGuardApp?.toast('You are signed in. Guest checks remain on this device.');
    });
    byId('accountImportButton')?.addEventListener('click', () => {
      closeModal('accountModal');
      openModal('authModal');
      showMigrationStage();
    });
    byId('exportAccountButton')?.addEventListener('click', exportAccount);
    byId('logoutButton')?.addEventListener('click', signOut);
    byId('showDeleteAccountButton')?.addEventListener('click', () => setHidden('deleteAccountConfirm', false));
    byId('deleteAccountInput')?.addEventListener('input', event => {
      if (byId('deleteAccountButton')) byId('deleteAccountButton').disabled = event.target.value !== 'DELETE';
    });
    byId('deleteAccountButton')?.addEventListener('click', deleteAccount);

    document.querySelectorAll('[data-auth-channel]').forEach(button =>
      button.addEventListener('click', () => setChannel(button.dataset.authChannel))
    );
    document.addEventListener('click', event => {
      const switchButton = event.target.closest('[data-switch-auth]');
      if (switchButton) openAuth(switchButton.dataset.switchAuth);
      const legalButton = event.target.closest('[data-open-legal]');
      if (legalButton) {
        closeModal('authModal');
        window.FXGuardApp?.showScreen(legalButton.dataset.openLegal);
      }
    });
    for (const modalId of ['authModal', 'accountModal']) {
      byId(modalId)?.addEventListener('click', event => {
        if (event.target === event.currentTarget) closeModal(modalId);
      });
    }
    document.addEventListener('keydown', event => {
      if (event.key !== 'Escape') return;
      closeModal('authModal');
      closeModal('accountModal');
    });
  }

  window.FXGuardAccount = {
    isSignedIn: () => Boolean(state.user),
    getChecks: () => state.user ? state.checks : null,
    saveCheck,
    clearChecks,
    deleteCheck,
    openSignUp: () => openAuth('signup'),
    updateUI,
  };

  bindEvents();
  restoreSession();
})();
