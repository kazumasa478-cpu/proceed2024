require("dotenv").config();
const axios = require("axios");
const Anthropic = require("@anthropic-ai/sdk");

const client = new Anthropic();

const username = process.env.WP_USER;
const password = process.env.WP_APP_PASSWORD;
const token = Buffer.from(`${username}:${password}`).toString("base64");

async function generateArticle(keyword) {
  const message = await client.messages.create({
    model: "claude-opus-4-7",
    max_tokens: 2048,
    messages: [
      {
        role: "user",
        content: `以下のキーワードについて、WordPressに投稿するSEOに強いブログ記事を日本語で書いてください。

キーワード: ${keyword}

出力形式（JSONで返してください）:
{
  "title": "記事タイトル",
  "content": "HTML形式の記事本文（h2/h3/p タグを使用）"
}

JSONのみ返してください。余分なテキストは不要です。`,
      },
    ],
  });

  const text = message.content[0].text.trim();
  const json = text.replace(/^```json\n?/, "").replace(/\n?```$/, "");
  return JSON.parse(json);
}

async function postToWordPress(title, content) {
  const res = await axios.post(
    `${process.env.WP_URL}/wp-json/wp/v2/posts`,
    {
      title,
      content,
      status: "draft",
    },
    {
      headers: {
        Authorization: `Basic ${token}`,
      },
    }
  );
  return res.data;
}

async function main() {
  const keyword = process.argv[2];
  if (!keyword) {
    console.error("使い方: node post.js <キーワード>");
    process.exit(1);
  }

  console.log(`キーワード: ${keyword}`);
  console.log("記事を生成中...");

  const { title, content } = await generateArticle(keyword);
  console.log(`タイトル: ${title}`);

  console.log("WordPressに投稿中...");
  const post = await postToWordPress(title, content);

  console.log("投稿成功！");
  console.log(`URL: ${post.link}`);
  console.log(`管理画面: ${process.env.WP_URL}/wp-admin/post.php?post=${post.id}&action=edit`);
}

main().catch((err) => {
  console.error(err.response?.data || err.message || err);
  process.exit(1);
});
