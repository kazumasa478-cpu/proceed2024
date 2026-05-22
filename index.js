require("dotenv").config();
const axios = require("axios");

const username = process.env.WP_USER;
const password = process.env.WP_APP_PASSWORD;

const token = Buffer.from(`${username}:${password}`).toString("base64");

async function postToWordPress() {
  const title = "Claude Codeから自動投稿";

  const content = `
<h2>自動投稿テスト</h2>

<p>これはClaude Codeから自動投稿された記事です。</p>
`;

  try {
    const res = await axios.post(
      `${process.env.WP_URL}/wp-json/wp/v2/posts`,
      {
        title,
        content,
        status: "draft"
      },
      {
        headers: {
          Authorization: `Basic ${token}`
        }
      }
    );

    console.log("投稿成功");
    console.log(res.data.link);

  } catch (err) {
    console.error(err.response?.data || err);
  }
}

postToWordPress();
