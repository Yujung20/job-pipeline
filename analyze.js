const Anthropic = require('@anthropic-ai/sdk');
const readline = require('readline');
const { execSync } = require('child_process'); 
const fs = require('fs');
const path = require('path');

const POSTS_DIR = 'D:\\project\\yujung20.github.io\\_posts';

async function askQuestion(prompt) {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });

  return new Promise((resolve) => {
    rl.question(prompt, (answer) => {
      rl.close();
      resolve(answer.trim());
    });
  });
}

async function readJobLink() {
  return askQuestion('공고 링크를 입력하세요: ');
}

function sanitizeFilenameToken(str) {
  return str
    .trim()
    .replace(/\s+/g, '-')
    .replace(/[^\w\-가-힣]/g, '');
}

async function readJobPosting() {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });

  console.log('\n링크드인 공고 원문 텍스트를 붙여넣으세요.');
  console.log('입력이 끝나면 새 줄에 "END" 를 입력하고 Enter 를 누르세요.\n');

  return new Promise((resolve) => {
    const lines = [];
    rl.on('line', (line) => {
      if (line.trim() === 'END') {
        rl.close();
        resolve(lines.join('\n'));
      } else {
        lines.push(line);
      }
    });
  });
}

async function analyzePosting(client, jobText) {
  const systemPrompt = `당신은 링크드인 채용 공고를 분석하는 전문가입니다.
주어진 채용 공고를 분석하여 다음 JSON 형식으로 정확히 응답하세요:

{
  "company": "회사명 (영문 그대로, 찾지 못한 경우 빈 문자열 \"\")",
  "role": "직무명 (영문 그대로, 찾지 못한 경우 빈 문자열 \"\")",
  "keywords": [
    "공고 원문에서 자주 등장하거나 핵심적인 단어/기술/역량을 영문 그대로 5~10개 추출 (예: Python, SQL, stakeholder management 등)"
  ],
  "summary_ko": "공고 전체 내용을 한국어로 요약 (회사 소개, 직무, 주요 업무, 복지 등을 4~8문장으로 정리)",
  "required_qualifications_ko": [
    "필수 지원 조건을 한국어로 번역한 항목들 (항목별로 분리)"
  ],
  "recommended_for_ko": "이 공고가 어떤 구직자에게 추천되는지 2~4문장으로 한국어 작성"
}

- company 와 role 은 파일명에 사용되므로 특수문자, 슬래시, 공백 없이 작성하세요 (공백은 하이픈으로 대체).
- 공고에서 회사명 또는 직무명을 명확하게 확인할 수 없는 경우 해당 필드는 추측하지 말고 빈 문자열 ""을 반환하세요.
- keywords 는 공고 원문 전체에서 반복적으로 등장하거나 이 직무의 핵심을 나타내는 단어/기술/역량을 영문 그대로 5개 이상 10개 이하로 추출하세요. 기술 스택, 도구, 직무 역량 등을 포함하세요.
- summary_ko 는 공고 전체를 한국어로 요약합니다. 회사 소개, 채용 직무, 주요 업무, 근무 조건 등을 자연스러운 문장으로 정리하세요.
- required_qualifications_ko 는 공고에서 Must have / Required / Qualifications 등의 필수 조건만 추출하세요.
- 반드시 JSON 만 응답하세요. 다른 텍스트는 포함하지 마세요.`;

  const response = await client.messages.create({
    model: 'claude-sonnet-4-6',
    max_tokens: 2000,
    system: [
      {
        type: 'text',
        text: systemPrompt,
        cache_control: { type: 'ephemeral' },
      },
    ],
    messages: [
      {
        role: 'user',
        content: `다음 채용 공고를 분석해주세요:\n\n${jobText}`,
      },
    ],
  });

  const raw = response.content[0].text.trim();

  const jsonMatch = raw.match(/\{[\s\S]*\}/);
  if (!jsonMatch) throw new Error('API 응답에서 JSON을 찾을 수 없습니다.');

  return JSON.parse(jsonMatch[0]);
}

function buildFrontmatter(date, company, role) {
  const title = `${company} - ${role}`;
  return `---
layout: post
title: "${title}"
date: ${date}
categories: [jobs]
tags: [linkedin, ${company.toLowerCase()}, ${role.toLowerCase()}]
---`;
}

function buildPostContent(frontmatter, jobLink, jobText, analysis) {
  const qualifications = analysis.required_qualifications_ko
    .map((q) => `- ${q}`)
    .join('\n');

  const keywords = (analysis.keywords || [])
    .map((k) => `\`${k}\``)
    .join(' ');

  return `${frontmatter}

## 공고 링크

${jobLink}

---

## 공고 원문

${jobText}

---

## 핵심 키워드

${keywords}

---

## 공고 요약

${analysis.summary_ko}

---

## 필수 지원 조건

${qualifications}

---

## 추천 대상

${analysis.recommended_for_ko}
`;
}
const STATS_PATH = 'D:\\project\\yujung20.github.io\\assets\\stats.json';

const SKILL_KEYWORDS = [
  'Python', 'SQL', 'Java', 'JavaScript', 'TypeScript', 'R', 'Scala', 'Go', 'C\\+\\+', 'C#',
  'AWS', 'GCP', 'Azure', 'Spark', 'Kafka', 'Airflow', 'Docker', 'Kubernetes',
  'TensorFlow', 'PyTorch', 'Tableau', 'PowerBI', 'dbt', 'Snowflake', 'Redshift', 'BigQuery',
  'React', 'Node\\.js', 'Django', 'FastAPI', 'PostgreSQL', 'MySQL', 'MongoDB', 'Redis',
  'Machine Learning', 'Deep Learning', 'NLP', 'Data Engineering', 'ETL', 'MLOps',
];

function extractSkills(qualifications) {
  const text = qualifications.join(' ');
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

function updateStats(newAnalysis, jobText) {
  let stats = { skillCount: {}, roleSkillMap: {}, skillPairs: {}, levelCount: {} };
  if (fs.existsSync(STATS_PATH)) {
    try {
      stats = JSON.parse(fs.readFileSync(STATS_PATH, 'utf8'));
      if (!stats.skillPairs) stats.skillPairs = {};
      if (!stats.levelCount) stats.levelCount = {};
    } catch (e) {}
  }

  // 스킬 카운트 누적
  const skills = extractSkills(newAnalysis.required_qualifications_ko);
  for (const [skill, count] of Object.entries(skills)) {
    stats.skillCount[skill] = (stats.skillCount[skill] || 0) + count;
  }

  // 직무별 스킬 맵 누적
  const role = newAnalysis.role;
  if (!stats.roleSkillMap[role]) stats.roleSkillMap[role] = {};
  for (const [skill, count] of Object.entries(skills)) {
    stats.roleSkillMap[role][skill] = (stats.roleSkillMap[role][skill] || 0) + count;
  }

  // 스킬 조합 누적
  const pairs = extractSkillPairs(skills);
  for (const [pair, count] of Object.entries(pairs)) {
    stats.skillPairs[pair] = (stats.skillPairs[pair] || 0) + count;
  }

  // 경력 수준 누적
  const level = extractLevel(`${newAnalysis.company} ${newAnalysis.role}`);
  stats.levelCount[level] = (stats.levelCount[level] || 0) + 1;

  fs.writeFileSync(STATS_PATH, JSON.stringify(stats, null, 2), 'utf8');
  console.log('\n📊 통계 업데이트 완료!');
}

function checkDuplicate(company, role) {
  const files = fs.readdirSync(POSTS_DIR);
  const key = `${company}-${role}`.toLowerCase();
  return files.some(file => file.toLowerCase().includes(key));
}

function savePost(date, company, role, content) {
  let filename = `${date}-${company}-${role}.md`;
  let filepath = path.join(POSTS_DIR, filename);

  let counter = 1;
  while (fs.existsSync(filepath)) {
    filename = `${date}-${company}-${role}-${counter}.md`;
    filepath = path.join(POSTS_DIR, filename);
    counter++;
  }

  fs.writeFileSync(filepath, content, 'utf8');
  return filepath;
}

async function main() {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    console.error('오류: ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.');
    process.exit(1);
  }

  const client = new Anthropic({ apiKey });

  const jobLink = await readJobLink();
  if (!jobLink) {
    console.error('오류: 공고 링크가 비어있습니다.');
    process.exit(1);
  }

  const jobText = await readJobPosting();
  if (!jobText.trim()) {
    console.error('오류: 공고 텍스트가 비어있습니다.');
    process.exit(1);
  }

  console.log('\n공고를 분석 중입니다...');

  let analysis;
  try {
    analysis = await analyzePosting(client, jobText);
  } catch (err) {
    console.error('분석 실패:', err.message);
    process.exit(1);
  }

  let company = (analysis.company || '').trim();
  let role = (analysis.role || '').trim();

  if (!company) {
    console.log('\n공고에서 회사명을 찾지 못했습니다.');
    while (!company) {
      const answer = await askQuestion('회사명을 입력하세요 (영문): ');
      company = sanitizeFilenameToken(answer);
      if (!company) console.log('회사명이 비어있습니다. 다시 입력하세요.');
    }
  }

  if (!role) {
    console.log('\n공고에서 직무명을 찾지 못했습니다.');
    while (!role) {
      const answer = await askQuestion('직무명을 입력하세요 (영문): ');
      role = sanitizeFilenameToken(answer);
      if (!role) console.log('직무명이 비어있습니다. 다시 입력하세요.');
    }
  }

  analysis.company = company;
  analysis.role = role;

  const today = new Date().toISOString().split('T')[0];
  const frontmatter = buildFrontmatter(today, company, role);
  const content = buildPostContent(frontmatter, jobLink, jobText, analysis);


  let savedPath;
  try {
    if (checkDuplicate(company, role)) {
      console.log(`\n⚠️  이미 "${company} - ${role}" 공고가 존재합니다.`);
      const answer = await askQuestion('그래도 저장할까요? (y/n): ');
      if (answer.toLowerCase() !== 'y') {
        console.log('저장을 취소했습니다.');
        process.exit(0);
      }
    }
    savedPath = savePost(today, company, role, content);
    updateStats(analysis, jobText); 
  } catch (err) {
    console.error('파일 저장 실패:', err.message);
    process.exit(1);
  }

  console.log('\n분석 완료!');
  console.log(`회사: ${company}`);
  console.log(`직무: ${role}`);
  console.log(`\n핵심 키워드: ${(analysis.keywords || []).join(', ')}`);
  console.log(`\n공고 요약:\n  ${analysis.summary_ko}`);
  console.log('\n필수 지원 조건:');
  analysis.required_qualifications_ko.forEach((q) => console.log(`  - ${q}`));
  console.log(`\n추천 대상:\n  ${analysis.recommended_for_ko}`);
  console.log(`\n저장 경로: ${savedPath}`);
  console.log('\nGitHub에 자동 업로드 중...');
  try {
    const BLOG_DIR = 'D:\\project\\yujung20.github.io';
    execSync('git add .', { cwd: BLOG_DIR, stdio: 'inherit' });
    execSync(`git commit -m "Add: ${company} - ${role}"`, { cwd: BLOG_DIR, stdio: 'inherit' });
    execSync('git push origin main', { cwd: BLOG_DIR, stdio: 'inherit' });
    console.log('\n✅ GitHub 업로드 완료! 블로그에 반영됐어요.');
  } catch (err) {
    console.error('\n❌ GitHub 업로드 실패:', err.message);
    console.log('수동으로 git push 해주세요.');
  }
}

main();