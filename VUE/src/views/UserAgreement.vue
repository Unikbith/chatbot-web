<script setup>
import { useRouter } from 'vue-router'
import brandIcon from '../assets/icon/ChatBotIcon.png'

const router = useRouter()
</script>

<template>
  <div class="ua-page">
    <header class="ua-header">
      <div class="ua-brand">
        <img :src="brandIcon" class="ua-logo" alt="Confide" />
        <span class="ua-brand-name">Confide · 心语</span>
      </div>
      <router-link to="/" class="ua-back">返回首页</router-link>
    </header>

    <main class="ua-main">
      <h1 class="ua-title">用户须知与免责声明</h1>
      <p class="ua-updated">最后更新日期：2026 年 10 月 3 日</p>

      <section class="ua-section">
        <h2>一、协议的接受</h2>
        <p>
          您在注册账号时勾选"已阅读并同意《用户须知与免责声明》"，即视为您已充分阅读、理解并自愿接受本声明的全部内容，本协议在您与平台之间成立。若您不同意本声明，请勿注册或使用本平台。
        </p>
      </section>

      <section class="ua-section">
        <h2>二、年龄与资格</h2>
        <p>
          本平台服务仅面向<strong>年满 18 周岁、具备完全民事行为能力</strong>的用户。若您未满 18 周岁，请勿注册或使用本平台。您声明并保证您符合上述条件。
        </p>
      </section>

      <section class="ua-section">
        <h2>三、服务性质（非盈利 / 按现状提供）</h2>
        <p>
          本平台为技术服务提供者，目前<strong>免费向用户提供服务，不以营利为目的</strong>。平台按"现状"和"可用"原则提供服务，不保证服务永久不间断、无故障、无错误或满足您的特定需求。
        </p>
      </section>

      <section class="ua-section">
        <h2>四、用户内容责任</h2>
        <p>
          您通过本平台输入、生成、发布、传播的一切内容（含对话、人物设定、图片、文本等），其<strong>合法性、真实性及后果由您独立承担全部法律责任</strong>。您承诺不利用本平台从事任何违反法律法规或公序良俗的活动。
        </p>
      </section>

      <section class="ua-section">
        <h2>五、禁止内容（合规红线）</h2>
        <p>您不得利用本平台制作、生成、传播任何违法或违规内容，包括但不限于：</p>
        <ul>
          <li>危害国家安全、泄露国家秘密、破坏国家统一；</li>
          <li>煽动民族仇恨、破坏民族团结，宣扬邪教或封建迷信；</li>
          <li>散布淫秽、色情、赌博、暴力、恐怖或教唆犯罪；</li>
          <li>侮辱、诽谤他人，侵害他人知识产权、名誉权、隐私权等合法权益；</li>
          <li><strong>任何侵害未成年人的内容（平台对此零容忍）；</strong></li>
          <li>其他违反中华人民共和国法律法规或公序良俗的内容。</li>
        </ul>
        <p>
          平台有权对违规内容进行处理，并随时终止违规账号的服务，且不承担由此产生的任何责任。
        </p>
      </section>

      <section class="ua-section">
        <h2>六、账号与行为责任</h2>
        <p>
          您的账号及密码由您妥善保管。凡通过您账号进行的一切操作，均视为您本人行为，由您承担相应后果与责任。请勿将账号转让、出借或共享给他人。
        </p>
      </section>

      <section class="ua-section">
        <h2>七、第三方服务</h2>
        <p>
          本平台可能接入第三方 AI 模型或服务，相关服务受其自身条款约束；平台不对第三方的服务内容、可用性及数据负责。
        </p>
      </section>

      <section class="ua-section">
        <h2>八、责任限制（免责）</h2>
        <p>在法律允许的最大范围内，平台对以下情形不承担责任：</p>
        <ul>
          <li>因不可抗力、网络故障、黑客攻击、病毒、系统维护或升级导致的服务中断、延迟、数据丢失；</li>
          <li>因您自身原因（如账号泄露、设备 / 网络问题）导致的损失；</li>
          <li>AI 生成内容可能存在的错误、不准确、不一致或不符合预期——平台不保证其准确性、完整性、适用性，相关内容仅供参考，不构成任何专业建议；</li>
          <li>任何间接、附带、特殊或后果性损害（包括但不限于利润、数据、商誉损失）。</li>
        </ul>
        <p>您因使用本平台产生的一切风险与责任由您自行承担。</p>
      </section>

      <section class="ua-section">
        <h2>九、声明的变更</h2>
        <p>
          平台有权根据法律法规或运营需要修改本声明，修改后的内容一经公示即生效。您继续使用本平台即视为接受修订后的内容。
        </p>
      </section>

      <section class="ua-section">
        <h2>十、争议解决</h2>
        <p>
          本声明的订立、解释与争议解决均适用中华人民共和国法律。因本声明产生的争议，双方应友好协商；协商不成的，提交平台运营方所在地有管辖权的人民法院诉讼解决。
        </p>
      </section>
    </main>

    <footer class="ua-footer">© Confide 心语 · 本声明解释权归平台运营方所有</footer>
  </div>
</template>

<style scoped>
.ua-page {
  height: 100vh;
  height: 100dvh;
  overflow-y: auto;
  background: var(--surface-hover, #faf7f4);
  color: var(--text-primary, #2a2522);
  display: flex;
  flex-direction: column;
}

.ua-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px;
  background: var(--surface, #fff);
  border-bottom: 1px solid var(--border-color, #e9e0d4);
  position: sticky;
  top: 0;
  z-index: 10;
}

.ua-brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

.ua-logo {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  object-fit: cover;
}

.ua-brand-name {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary, #2a2522);
}

.ua-back {
  font-size: 14px;
  color: var(--brand, #b06a2e);
  text-decoration: none;
  font-weight: 500;
}

.ua-back:hover {
  text-decoration: underline;
}

.ua-main {
  flex: 1;
  width: 100%;
  max-width: 760px;
  margin: 0 auto;
  padding: 32px 24px 48px;
}

.ua-title {
  font-size: 24px;
  font-weight: 700;
  margin: 0 0 6px;
  color: var(--text-primary, #2a2522);
}

.ua-updated {
  font-size: 13px;
  color: var(--text-muted, #a9815a);
  margin: 0 0 24px;
}

.ua-section {
  margin-bottom: 24px;
}

.ua-section h2 {
  font-size: 16px;
  font-weight: 600;
  margin: 0 0 8px;
  color: var(--brand, #b06a2e);
}

.ua-section p {
  font-size: 14px;
  line-height: 1.8;
  margin: 0 0 8px;
  color: var(--text-secondary, #5a4f44);
}

.ua-section ul {
  margin: 0;
  padding-left: 20px;
}

.ua-section li {
  font-size: 14px;
  line-height: 1.8;
  color: var(--text-secondary, #5a4f44);
}

.ua-footer {
  text-align: center;
  font-size: 12px;
  color: var(--text-muted, #a9815a);
  padding: 24px;
  border-top: 1px solid var(--border-color, #e9e0d4);
  background: var(--surface, #fff);
}

@media (max-width: 600px) {
  .ua-main {
    padding: 24px 16px 40px;
  }
  .ua-title {
    font-size: 21px;
  }
}
</style>
