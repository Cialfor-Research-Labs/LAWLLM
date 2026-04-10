#!/usr/bin/env node

const nodemailer = require('nodemailer');

async function main() {
  const [, , toEmail, recipientName, setupUrl] = process.argv;
  if (!toEmail || !setupUrl) {
    console.error('Usage: node send_setup_email.cjs <toEmail> <recipientName> <setupUrl>');
    process.exit(1);
  }

  const smtpHost = process.env.SMTP_HOST;
  const smtpPort = Number(process.env.SMTP_PORT || '587');
  const smtpUser = process.env.SMTP_USER;
  const smtpPass = process.env.SMTP_PASS;
  const smtpFrom = process.env.SMTP_FROM || smtpUser;
  const smtpSecure = String(process.env.SMTP_SECURE || 'false').toLowerCase() === 'true';

  if (!smtpHost || !smtpUser || !smtpPass || !smtpFrom) {
    console.error('Missing SMTP env vars. Required: SMTP_HOST, SMTP_USER, SMTP_PASS, SMTP_FROM');
    process.exit(1);
  }

  const transporter = nodemailer.createTransport({
    host: smtpHost,
    port: smtpPort,
    secure: smtpSecure,
    auth: {
      user: smtpUser,
      pass: smtpPass,
    },
  });

  const name = recipientName || 'User';
  const info = await transporter.sendMail({
    from: smtpFrom,
    to: toEmail,
    subject: 'Vidhi AI Access: Set your password',
    text: `Hello ${name},\n\nYour access has been approved. Set your password using this link:\n${setupUrl}\n\nIf you did not request this, ignore this email.\n`,
    html: `
      <p>Hello ${name},</p>
      <p>Your Vidhi AI access has been approved.</p>
      <p>Set your password using this link:</p>
      <p><a href="${setupUrl}">${setupUrl}</a></p>
      <p>If you did not request this, you can ignore this email.</p>
    `,
  });

  console.log(JSON.stringify({ ok: true, messageId: info.messageId }));
}

main().catch((err) => {
  console.error(err?.message || String(err));
  process.exit(1);
});

