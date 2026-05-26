require("dotenv").config();

const fs = require("fs");
const axios = require("axios");

const Anthropic = require("@anthropic-ai/sdk");
const OpenAI = require("openai");

const { TwitterApi } = require("twitter-api-v2");

const anthropic = new Anthropic({
  apiKey: process.env.ANTHROPIC_API_KEY,
});

const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
});

const twitterClient = new TwitterApi({
  appKey: process.env.X_API_KEY,
  appSecret: process.env.X_API_SECRET,
  accessToken: process.env.X_ACCESS_TOKEN,
  accessSecret: process.env.X_ACCESS_SECRET,
});

const keyword = process.argv[2];

async function run() {

  // =====================
  // Claude記事生成
  // =====================

  const msg = await anthropic.messages.create({
    model: "claude-sonnet-4-6",
    max_tokens: 4000,
    messages: [
      {
        role: "user",
        content:
`「${keyword}」について
SEOに強いブログ記事を書いて。

条件：
- 1000文字以上
- H2/H3見出し
- 読みやすい
- 専門性あり
- HTML形式`
      }
    ]
  });

  const article = msg.content[0].text
    .replace(/^```html\s*/i, "")
    .replace(/```\s*$/, "")
    .trim();

  console.log("記事生成完了");

  // =====================
  // 画像生成
  // =====================

  const imageRes = await openai.images.generate({
    model: "dall-e-3",
    prompt: `${keyword}のブログ用アイキャッチ画像`,
    size: "1792x1024",
  });

  const imageUrl = imageRes.data[0].url;

  const imageData = await axios.get(imageUrl, {
    responseType: "arraybuffer",
  });

  fs.mkdirSync("./images", { recursive: true });
  fs.writeFileSync("./images/thumbnail.png", imageData.data);

  console.log("画像生成完了");

  // =====================
  // WordPress認証
  // =====================

  const token = Buffer
    .from(
      `${process.env.WP_USER}:${process.env.WP_APP_PASSWORD}`
    )
    .toString("base64");

  // =====================
  // 画像アップロード
  // =====================

  const mediaRes = await axios.post(
    `${process.env.WP_URL}/wp-json/wp/v2/media`,
    fs.readFileSync("./images/thumbnail.png"),
    {
      headers: {
        Authorization: `Basic ${token}`,
        "Content-Type": "image/png",
        "Content-Disposition":
          'attachment; filename="thumbnail.png"',
      },
    }
  );

  const mediaId = mediaRes.data.id;

  console.log("画像アップロード完了");

  // =====================
  // WordPress投稿
  // =====================

  const postRes = await axios.post(
    `${process.env.WP_URL}/wp-json/wp/v2/posts`,
    {
      title: keyword,
      content: article,
      status: "draft",
      featured_media: mediaId,
    },
    {
      headers: {
        Authorization: `Basic ${token}`,
      },
    }
  );

  const postUrl = postRes.data.link;

  console.log("WordPress投稿完了");

  // =====================
  // X投稿（一旦オフ）
  // =====================

  // await twitterClient.v2.tweet(
  //   `新記事公開\n${keyword}\n${postUrl}`
  // );
  // console.log("X投稿完了");
}

run();
