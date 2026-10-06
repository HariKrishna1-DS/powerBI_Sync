function redact(message, secrets = []) {
  let output = String(message?.message || message);
  const values = [...secrets];
  for (const secret of secrets) {
    if (!secret) continue;
    try {
      const account = JSON.parse(secret);
      values.push(account.private_key, account.private_key_id);
    } catch { /* Most configured secrets are plain strings. */ }
  }
  for (const secret of values.filter(value => typeof value === 'string' && value).sort((a, b) => b.length - a.length)) {
    output = output.split(secret).join('[redacted]').split(secret.replaceAll('\n', '\\n')).join('[redacted]');
  }
  return output.replace(/-----BEGIN (?:RSA )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA )?PRIVATE KEY-----/g, '[redacted private key]');
}
module.exports = {redact};
