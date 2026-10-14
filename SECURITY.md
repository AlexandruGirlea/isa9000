# Security

## Reporting a vulnerability

Email **alex@girlea.ro**. Do not open a public issue.

Expect an acknowledgement within 3 working days and a fix or a plan within 30.

## Scope

isa9000 runs on the machine it is installed on. Besides reading the links
you add, it sends only what the models need (your request, the content of your
sources, the scripts to record and short clips of each recording) to the Google
or Azure model endpoints in your configuration, and nothing to any other network service
apart from signing in to them. Reports of any other data leaving the
machine are treated as critical.

Also in scope:

- the audio generation UI answering anything but local requests, or accepting
  cross-site writes;
- reading files outside the sources the user chose;
- credentials from `isa9000.toml` appearing in logs, `podcast.json`, the
  presentation website or any other output;
- local file paths appearing on the presentation website;
- script injection through source content, podcast titles or transcripts on the
  presentation website.

## Supported versions

The latest release only.
