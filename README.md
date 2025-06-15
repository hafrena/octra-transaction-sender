# Octra Transaction Sender CLI

A lightweight command-line tool for sending and viewing transactions on the Octra blockchain network.

---

## 🔧 Features

- ✅ Local signing with your private key (never sent anywhere)
- ✅ Pretty logs with tx hash, from/to, amount, epoch, validator
- ✅ Status check: pending vs. finalized
- ✅ View transaction by hash via RPC or Octrascan

---

## 🛠 Requirements

- Python 3.8+
- Install dependencies:

```bash
pip install -r requirements.txt

Create .env file in the root folder / Создай файл .env в корне проекта:

PRIVATE_KEY=your_base64_encoded_private_key_here
FROM_ADDRESS=your_oct_wallet_address_here