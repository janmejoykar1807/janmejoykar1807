// update_readme.js — called by GitHub Action
// Reads profile.json + current README, calls GitHub Models, writes updated README

const fs = require('fs');
const https = require('https');

async function main() {
  // ── Read inputs ──────────────────────────────────────────────────────
  const profile = JSON.parse(fs.readFileSync('profile.json', 'utf-8'));
  const currentReadme = fs.existsSync('README.md')
    ? fs.readFileSync('README.md', 'utf-8')
    : '';

  console.log(`Profile loaded: ${profile.basics?.name}`);
  console.log(`Certs: ${profile.certifications?.length} | Pubs: ${profile.publications?.length} | Projects: ${profile.projects?.length}`);

  // ── Build prompt ─────────────────────────────────────────────────────
  const prompt = [
    'You are a GitHub README updater for a developer profile.',
    '',
    'CURRENT README:',
    currentReadme,
    '',
    'UPDATED PROFILE DATA (JSON):',
    JSON.stringify(profile, null, 2),
    '',
    'INSTRUCTIONS:',
    '- Preserve ALL existing visual elements: animated SVG banners, shields.io badges, career journey visualizations, layout',
    '- Update ONLY these sections with new data: Publications, Certifications, Projects, Experience, Skills, Bio',
    '- If a section does not exist yet, add it in an appropriate place',
    '- Keep the same formatting style as the existing README',
    '- For publications: include title, journal, year, and URL',
    '- For certifications: distinguish active vs in-progress',
    '- Return ONLY the complete updated README markdown — no explanation, no code fences'
  ].join('\n');

  // ── Call GitHub Models API ───────────────────────────────────────────
  const requestBody = JSON.stringify({
    model: 'gpt-4o-mini',
    messages: [
      {
        role: 'system',
        content: 'You are a GitHub README updater. Return only valid markdown. No explanation. No code fences.'
      },
      {
        role: 'user',
        content: prompt
      }
    ],
    max_tokens: 4000,
    temperature: 0.3
  });

  const options = {
    hostname: 'models.inference.ai.azure.com',
    path: '/chat/completions',
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${process.env.GITHUB_TOKEN}`,
      'Content-Length': Buffer.byteLength(requestBody)
    }
  };

  console.log('Calling GitHub Models (gpt-4o-mini)...');

  const newReadme = await new Promise((resolve, reject) => {
    const req = https.request(options, res => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          if (parsed.error) {
            reject(new Error(`GitHub Models error: ${parsed.error.message}`));
          } else {
            const content = parsed.choices[0].message.content.trim();
            resolve(content);
          }
        } catch (e) {
          reject(new Error(`Parse error: ${e.message} — Response: ${data.slice(0, 300)}`));
        }
      });
    });
    req.on('error', reject);
    req.write(requestBody);
    req.end();
  });

  // ── Write updated README ─────────────────────────────────────────────
  fs.writeFileSync('README.md', newReadme, 'utf-8');
  console.log(`README updated successfully — ${newReadme.length} chars written`);
}

main().catch(err => {
  console.error('Error:', err.message);
  process.exit(1);
});
