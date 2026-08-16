const crypto = require('crypto');
const { AE } = require('./constants');

/**
 * Encrypts data using AES-128-CBC with PKCS7 padding.
 * @param {Buffer} buffer - The data to encrypt
 * @returns {Buffer} Encrypted data
 */
function encrypt(buffer) {
    const cipher = crypto.createCipheriv('aes-128-cbc', AE.MAIN_KEY, AE.MAIN_IV);
    const encrypted = Buffer.concat([cipher.update(buffer), cipher.final()]);
    return encrypted;
}

module.exports = { encrypt };
