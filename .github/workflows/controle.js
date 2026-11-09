// Contrôle de l'appli H2H Tennis, exécuté par GitHub Actions (controle.yml).
// Passage 1, sans code : captures d'écran (données publiques seulement).
// Passage 2, avec le code : chiffres de contrôle, sans capture (données Cito et TennisMyLife non publiées).
// Résultat : rapport/controle/controle.md, controle.json et captures *.png.
const { chromium } = require("playwright");
const fs = require("fs");

const URL_APPLI = "http://localhost:8000/index.html";
const SORTIE = "rapport/controle";
const A = "s206173", B = "s207989";   // Sinner, Alcaraz (identifiants de l'archive)
const rapport = { date: new Date().toISOString(), version_appli: null, passages: {}, erreurs: [], alertes: [] };

async function ouvrir(navigateur, avecCode) {
  const page = await navigateur.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
  const erreurs = [];
  page.on("pageerror", e => erreurs.push("page : " + e.message));
  page.on("console", m => { if (m.type() === "error") erreurs.push("console : " + m.text()); });
  page.on("requestfailed", r => { if (!/wikimedia|wikipedia/.test(r.url())) erreurs.push("réseau : " + r.url()); });
  const t0 = Date.now();
  await page.goto(URL_APPLI);
  // le code est demandé à la première ouverture
  const modal = await page.waitForSelector("#code", { timeout: 60000 }).catch(() => null);
  if (modal) {
    if (avecCode && process.env.CODE_TML) { await page.fill("#code", process.env.CODE_TML); await page.click("#ok"); }
    else await page.click("#passer");
  }
  await page.waitForFunction(() => !document.querySelector("#charge"), null, { timeout: 180000 });
  return { page, erreurs, duree: (Date.now() - t0) / 1000 };
}

async function capture(page, hash, nom) {
  await page.evaluate(h => { location.hash = h; }, hash);
  await page.waitForTimeout(2500);
  await page.waitForFunction(() => !/Chargement…/.test(document.body.innerText), null, { timeout: 60000 }).catch(() => {});
  await page.screenshot({ path: `${SORTIE}/${nom}.png`, fullPage: true });
}

function chiffres() {
  // exécuté dans la page
  const cle = m => D.T[m.t].id + "|" + m.g + "|" + m.p + "|" + m.tour;
  const vus = new Map(); let doublons = 0;
  for (const m of D.M) { const k = cle(m); if (vus.has(k)) doublons++; else vus.set(k, 1); }
  const depuis = "2026-06-01";
  const parCat = {};
  for (const m of D.M) {
    if (m.d < depuis) continue;
    const n = D.T[m.t].niv, q = /^Q/.test(m.tour);
    const c = n === "C" ? (q ? "Challenger qualifications" : "Challenger tableau") : n.startsWith("I") ? "ITF" : (q ? "ATP qualifications" : "ATP tableau");
    const x = parCat[c] || (parCat[c] = { matchs: 0, score_complet: 0, stats: 0 });
    x.matchs++; if (m.dr & 7) x.score_complet++; if (m.st && m.st[1] != null) x.stats++;
  }
  for (const x of Object.values(parCat)) { x.score_complet_pct = Math.round(1000 * x.score_complet / x.matchs) / 10; }
  return {
    version_appli: typeof VERSION_APPLI !== "undefined" ? VERSION_APPLI : null,
    matchs: D.M.length, joueurs: D.J.size, tournois: D.T.length, doublons,
    complements_dechiffres: !!D.chiffre,
    classement: D.rang ? { semaine: D.rang.semaine, source: D.rang.source, rangs: D.rang.liste.length, top3: D.rang.liste.slice(0, 3).map(x => [x[0], (D.J.get(x[1]) || {}).nom || x[1], x[2]]) } : null,
    photos: Object.values(D.photos || {}).filter(p => p[2]).length,
    joueurs_avec_poids: Object.values(D.photos || {}).filter(p => p[6]).length,
    sinner: { nom: (D.J.get("s206173") || {}).nom, matchs: (D.parJoueur.get("s206173") || []).length, photo: !!(D.photos["s206173"] || [])[2] },
    depuis_juin: parCat,
  };
}

(async () => {
  fs.mkdirSync(SORTIE, { recursive: true });
  for (const f of fs.readdirSync(SORTIE)) if (f.endsWith(".png")) fs.unlinkSync(`${SORTIE}/${f}`);
  const nav = await chromium.launch();
  try {
    // passage 1 : sans code, avec captures
    const p1 = await ouvrir(nav, false);
    rapport.passages.public = { duree_chargement_s: p1.duree, chiffres: await p1.page.evaluate(chiffres) };
    await p1.page.screenshot({ path: `${SORTIE}/1-accueil.png`, fullPage: true });
    await capture(p1.page, `/joueur/${A}`, "2-joueur");
    await capture(p1.page, `/h2h/${A}/${B}`, "3-face-a-face");
    const tid = await p1.page.evaluate(() => { const m = D.M.filter(x => x.tour === "F").sort((a, b) => a.d < b.d ? 1 : -1)[0]; return m ? D.T[m.t].id : null; });
    if (tid) await capture(p1.page, `/tournoi/${tid}`, "4-tournoi");
    rapport.erreurs.push(...p1.erreurs.map(e => "sans code · " + e));
    await p1.page.close();
    // passage 2 : avec code, chiffres seulement
    if (process.env.CODE_TML) {
      const p2 = await ouvrir(nav, true);
      const c = await p2.page.evaluate(chiffres);
      rapport.passages.complet = { duree_chargement_s: p2.duree, chiffres: c };
      if (!c.complements_dechiffres) rapport.alertes.push("compléments chiffrés non déchiffrés avec le code du secret CODE_TML");
      rapport.erreurs.push(...p2.erreurs.map(e => "avec code · " + e));
    } else rapport.alertes.push("secret CODE_TML absent : passage complet sauté");
    const c = (rapport.passages.complet || rapport.passages.public).chiffres;
    rapport.version_appli = c.version_appli;
    if (c.doublons) rapport.alertes.push(`${c.doublons} matchs en double`);
    if (!c.classement || c.classement.rangs < 100) rapport.alertes.push("classement absent ou de moins de 100 rangs");
  } catch (e) {
    rapport.erreurs.push("contrôle interrompu : " + e.message);
  } finally {
    await nav.close();
  }
  const ok = !rapport.erreurs.length;
  fs.writeFileSync(`${SORTIE}/controle.json`, JSON.stringify(rapport, null, 1));
  const md = [`# Contrôle de l'appli`, ``, `- Date (UTC) : ${rapport.date}`, `- Version de l'appli : ${rapport.version_appli}`,
    `- État : **${ok ? (rapport.alertes.length ? "OK avec alertes" : "OK") : "ERREURS"}**`, ``,
    `## Erreurs`, ...(rapport.erreurs.length ? rapport.erreurs.map(e => "- " + e) : ["- aucune"]), ``,
    `## Alertes`, ...(rapport.alertes.length ? rapport.alertes.map(e => "- " + e) : ["- aucune"]), ``,
    `## Chiffres`, "```json", JSON.stringify(rapport.passages, null, 1), "```", ``,
    `## Captures (sans code, données publiques)`, `![accueil](1-accueil.png) ![joueur](2-joueur.png) ![face-à-face](3-face-a-face.png) ![tournoi](4-tournoi.png)`];
  fs.writeFileSync(`${SORTIE}/controle.md`, md.join("\n"));
  console.log(md.slice(0, 12).join("\n"));
  process.exit(ok ? 0 : 1);
})();
