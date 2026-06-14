const fs = require('fs');
const path = require('path');

const POSTS_DIR = 'D:\\project\\yujung20.github.io\\_posts';
const STATS_PATH = 'D:\\project\\yujung20.github.io\\assets\\stats.json';

const SKILL_KEYWORDS = [
  'Python', 'SQL', 'Java', 'JavaScript', 'TypeScript', 'R', 'Scala', 'Go', 'C\\+\\+', 'C#',
  'AWS', 'GCP', 'Azure', 'Spark', 'Kafka', 'Airflow', 'Docker', 'Kubernetes',
  'TensorFlow', 'PyTorch', 'Tableau', 'PowerBI', 'dbt', 'Snowflake', 'Redshift', 'BigQuery',
  'React', 'Node\\.js', 'Django', 'FastAPI', 'PostgreSQL', 'MySQL', 'MongoDB', 'Redis',
  'Machine Learning', 'Deep Learning', 'NLP', 'Data Engineering', 'ETL', 'MLOps',
];

function extractSkills(text) {
  const found = {};
  for (const skill of SKILL_KEYWORDS) {
    const regex = new RegExp(skill, 'i');
    if (regex.test(text)) {
      const cleanName = skill.replace(/\\\./g, '.').replace(/\\\+/g, '+');
      found[cleanName] = (found[cleanName] || 0) + 1;
    }
  }
  return found;
}

function extractSkillPairs(skills) {
  const keys = Object.keys(skills);
  const pairs = {};
  for (let i = 0; i < keys.length; i++) {
    for (let j = i + 1; j < keys.length; j++) {
      const pair = [keys[i], keys[j]].sort().join(' + ');
      pairs[pair] = (pairs[pair] || 0) + 1;
    }
  }
  return pairs;
}

function extractLevel(text) {
  const levels = [
    ['Intern', /intern/i],
    ['Senior', /senior/i],
    ['Junior', /junior/i],
    ['Mid', /\bmid[\s-]?level|\bmid\b/i],
    ['Entry', /entry[\s-]?level/i],
  ];
  for (const [level, regex] of levels) {
    if (regex.test(text)) return level;
  }
  return 'Unknown';
}

function extractSection(content, sectionTitle) {
  const regex = new RegExp(`## ${sectionTitle}\\s*\\n([\\s\\S]*?)(?=\\n## |$)`);
  const match = content.match(regex);
  return match ? match[1].trim() : '';
}

function extractRoleFromFilename(filename) {
  const base = path.basename(filename, path.extname(filename));
  const parts = base.split('-');
  if (parts.length < 5) return null;
  return parts.slice(4).join('-');
}

function rebuildStats() {
  const stats = { skillCount: {}, roleSkillMap: {}, skillPairs: {}, levelCount: {} };

  const files = fs.readdirSync(POSTS_DIR).filter(f => f.endsWith('.md') || f.endsWith('.markdown'));
  let processed = 0;
  let skipped = 0;

  for (const file of files) {
    const filepath = path.join(POSTS_DIR, file);
    const content = fs.readFileSync(filepath, 'utf8');

    const qualSection = extractSection(content, '필수 지원 조건');
    if (!qualSection) {
      console.log(`  ⏭  스킵 (필수 조건 없음): ${file}`);
      skipped++;
      continue;
    }

    const role = extractRoleFromFilename(file);
    if (!role) {
      console.log(`  ⏭  스킵 (직무명 파싱 불가): ${file}`);
      skipped++;
      continue;
    }

    const skills = extractSkills(qualSection);
    if (Object.keys(skills).length === 0) {
      console.log(`  ⏭  스킵 (스킬 키워드 없음): ${file}`);
      skipped++;
      continue;
    }

    for (const [skill, count] of Object.entries(skills)) {
      stats.skillCount[skill] = (stats.skillCount[skill] || 0) + count;
    }

    if (!stats.roleSkillMap[role]) stats.roleSkillMap[role] = {};
    for (const [skill, count] of Object.entries(skills)) {
      stats.roleSkillMap[role][skill] = (stats.roleSkillMap[role][skill] || 0) + count;
    }

    const pairs = extractSkillPairs(skills);
    for (const [pair, count] of Object.entries(pairs)) {
      stats.skillPairs[pair] = (stats.skillPairs[pair] || 0) + count;
    }

    const titleMatch = content.match(/^title:\s*"(.+?)"/m);
    const titleText = titleMatch ? titleMatch[1] : file;
    const level = extractLevel(titleText);
    stats.levelCount[level] = (stats.levelCount[level] || 0) + 1;

    console.log(`  ✅ 처리됨: ${file} → 스킬 ${Object.keys(skills).length}개 / 레벨: ${level}`);
    processed++;
  }

  fs.writeFileSync(STATS_PATH, JSON.stringify(stats, null, 2), 'utf8');

  console.log('\n=============================');
  console.log(`✅ 완료! 처리된 공고: ${processed}개 / 스킵: ${skipped}개`);
  console.log(`📊 stats.json 저장됨: ${STATS_PATH}`);
  console.log('=============================');
}

rebuildStats();