# Privacy policy — A3 Training Coach (test)

This policy covers the "A3 Training Coach (test)" Google OAuth application, a student project
for CSCI 599 (Agentic AI, Fall 2026). The application is not offered to the public.

## Who uses it

Only a dedicated test Google account created for this course project. It is not used with
any personal, university or third-party account.

## What data it accesses

With the permissions granted by that test account, the assistant:

- reads messages in the test Gmail inbox to summarize them and draft replies;
- sends an email only after the account owner approves that specific draft with a one-time
  code, and only to an allow-listed test address;
- reads events from the test Google Calendar to plan training sessions and send reminders.

All mailbox and calendar content is synthetic test data.

## Where data goes

Data is processed by the assistant running in the owner's private Google Cloud project and,
for language-model responses, by the owner's configured model providers (OpenAI through the
owner's ChatGPT workspace, and a Gemma model running on the owner's own computer). It is not
sold, shared with or disclosed to anyone else, and it is not used for advertising.

## Storage and deletion

Working state (drafts, reminder history, assistant memory) is kept in a private Cloud Storage
bucket in the owner's project. Credentials are kept in Google Secret Manager. Everything is
deleted when the course project ends; access can be revoked at any time from the test
account's Google Account → Security → Third-party access.

## Contact

Open an issue in this repository:
https://github.com/is-ClarkHu/hermes-training-hub-skill/issues
