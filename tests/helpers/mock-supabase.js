/**
 * Supabase CDN をインメモリモックに差し替える。
 * - 認証: 偽セッションを即座に返す（Google OAuth なし）
 * - DB: upsert/select はすべて no-op、localStorage のみ使用
 */
const MOCK_SCRIPT = `
window.supabase = {
  createClient: function(url, key) {
    return {
      auth: {
        onAuthStateChange: function(cb) {
          const fakeUser = {
            id: 'test-user-local',
            email: 'test@local.test',
            user_metadata: { full_name: 'Test User' }
          };
          setTimeout(() => cb('SIGNED_IN', { user: fakeUser }), 30);
          return { data: { subscription: { unsubscribe: function() {} } } };
        },
        signInWithOAuth: function() { return Promise.resolve({}); },
        signOut: function() { return Promise.resolve({}); }
      },
      from: function(table) {
        return {
          upsert: function(data, opts) {
            return Promise.resolve({ error: null });
          },
          select: function(cols) {
            return {
              eq: function(col, val) {
                return {
                  eq: function(col2, val2) {
                    return Promise.resolve({ data: [], error: null });
                  }
                };
              }
            };
          }
        };
      }
    };
  }
};
`;

async function mockSupabase(page) {
  await page.route('**supabase**', route => {
    route.fulfill({ contentType: 'application/javascript', body: MOCK_SCRIPT });
  });
}

/**
 * アプリの初期化完了を待つ（words.json ロード + カード表示）
 */
async function waitForAppReady(page) {
  await page.waitForFunction(() =>
    typeof allWords !== 'undefined' &&
    allWords.length > 0 &&
    document.getElementById('cardCounter') !== null
  , { timeout: 10000 });
}

/**
 * 全単語をセッション完了状態にする（全語 known 扱い）
 */
async function setupAllDone(page) {
  await page.evaluate(() => {
    allWords.forEach(w => { w.status = 'green'; });
    // 進捗タブを再描画してもう一回ボタンを有効化
    renderProgress();
    // 完了画面を表示（本番と同じ状態: cardQueue は allWords のまま）
    cardIndex = allWords.length;
    showDoneScreen();
  });
}

module.exports = { mockSupabase, waitForAppReady, setupAllDone };
