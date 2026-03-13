/**
 * 進捗タブ「もう一回」テスト
 *
 * テスト対象:
 *   - 進捗タブに今日の単語一覧が表示されること
 *   - 「もう一回」ボタンで単語を再学習キューに追加できること
 *   - 「もう一回（全部）」で全語を再学習できること
 *   - カード学習タブのカウンターがキューを正確に反映すること
 *
 * テスト方針:
 *   - Supabase CDN をモックに差し替え（本番DB影響ゼロ）
 *   - Google 認証をスキップ（偽セッションを即座に注入）
 */

const { test, expect } = require('@playwright/test');
const { mockSupabase, waitForAppReady, setupAllDone } = require('./helpers/mock-supabase');

// ── ヘルパー ────────────────────────────────────────────────

async function goToProgress(page) {
  await page.click('button[data-tab="progress"]');
}

async function goToCards(page) {
  await page.click('button[data-tab="card"]');
}

async function getCounter(page) {
  return page.locator('#cardCounter').textContent();
}

/** 進捗タブで指定IDの「もう一回」ボタンをクリック */
async function clickMouIkkai(page, wordId) {
  await page.locator(`#todayList .mouikkai-btn[data-word-id="${wordId}"]`).click();
}

// ── セットアップ ────────────────────────────────────────────

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.clear());
  await mockSupabase(page);
  await page.goto('/');
  await waitForAppReady(page);
  await setupAllDone(page);
});

// ── T1: 今日の単語リスト表示 ────────────────────────────────

test('T1: 進捗タブに今日の単語リストが表示される', async ({ page }) => {
  await goToProgress(page);
  const list = page.locator('#todayList');
  await expect(list).toBeVisible();

  const items = list.locator('.today-item');
  const wordCount = await page.evaluate(() => allWords.length);
  await expect(items).toHaveCount(wordCount);
});

// ── T2: ステータスバッジが正しく表示される ──────────────────

test('T2: green ステータスの単語に ✅ バッジが表示される', async ({ page }) => {
  await goToProgress(page);
  const firstBadge = page.locator('#todayList .today-item').first().locator('.status-badge');
  await expect(firstBadge).toHaveText('✅');
});

// ── T3: 単語1語「もう一回」→ カウンターが 1/1 ──────────────

test('T3: 「もう一回」×1 → カード学習タブのカウンターが 1/1', async ({ page }) => {
  await goToProgress(page);

  const firstId = await page.evaluate(() => allWords[0].id);
  await clickMouIkkai(page, firstId);
  await goToCards(page);

  await expect(page.locator('#cardCounter')).toHaveText('1 / 1');
});

// ── T4: 2語「もう一回」→ カウンターが 1/2 ──────────────────

test('T4: 「もう一回」×2 → カード学習タブのカウンターが 1/2', async ({ page }) => {
  await goToProgress(page);

  const ids = await page.evaluate(() => [allWords[0].id, allWords[1].id]);
  await clickMouIkkai(page, ids[0]);
  await clickMouIkkai(page, ids[1]);
  await goToCards(page);

  await expect(page.locator('#cardCounter')).toHaveText('1 / 2');
});

// ── T5: 同じ単語を2回押したらトグルでキャンセル ───────────

test('T5: 「もう一回」→「✓ キュー済」→ もう一度押すとキャンセルされる', async ({ page }) => {
  await goToProgress(page);

  const firstId = await page.evaluate(() => allWords[0].id);
  const btn = page.locator(`#todayList .mouikkai-btn[data-word-id="${firstId}"]`);

  // 1回目: キューに追加 → ボタンが「✓ キュー済」に変わる
  await btn.click();
  await expect(btn).toHaveText('✓ キュー済');
  await expect(btn).toHaveClass(/queued/);

  // 2回目: キューから削除 → ボタンが「もう一回」に戻る
  await btn.click();
  await expect(btn).toHaveText('もう一回');
  await expect(btn).not.toHaveClass(/queued/);

  // カードタブに移動してもキューに追加されていない
  await goToCards(page);
  await expect(page.locator('#doneScreen')).toBeVisible();
});

// ── T6: 「もう一回（全部）」→ 全語がキューに入る ───────────

test('T6: 「もう一回（全部）」→ カードタブで全語 1/N', async ({ page }) => {
  await goToProgress(page);
  await page.click('#mouikkaiAll');

  // switchTab('card') が自動で呼ばれるのでカードタブに切り替わる
  await page.waitForSelector('#cardCounter', { timeout: 3000 });

  const wordCount = await page.evaluate(() => allWords.length);
  await expect(page.locator('#cardCounter')).toHaveText(`1 / ${wordCount}`);
});

// ── T7: タブ往復してもキューが保持される ────────────────────

test('T7: もう一回→進捗確認→もう一回追加→カードタブで 1/2', async ({ page }) => {
  await goToProgress(page);

  const ids = await page.evaluate(() => [allWords[0].id, allWords[1].id]);
  await clickMouIkkai(page, ids[0]);

  // 一度カードタブへ
  await goToCards(page);
  await expect(page.locator('#cardCounter')).toHaveText('1 / 1');

  // 完了画面になっているため進捗タブに戻り2語目追加
  await goToProgress(page);
  await clickMouIkkai(page, ids[1]);
  await goToCards(page);

  await expect(page.locator('#cardCounter')).toHaveText('1 / 2');
});

// ── T8: 完了画面が表示されている ────────────────────────────

test('T8: 全語 known → 完了画面が表示される', async ({ page }) => {
  await expect(page.locator('#doneScreen')).toBeVisible();
});
