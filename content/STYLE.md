# Illustration and audio style

So every lesson looks like part of one app, whoever makes its pictures.

## Illustrations

- **Flat illustration**: solid colours, no outlines, no gradients or textures, soft shapes. Simple enough to read at phone size.
- **4:3, at least 1200 × 900.** Wider images are shrunk to 1600px wide when uploaded; other shapes are shown whole with space around them.
- **One clear subject**, centred, on a plain light background with a large soft circle behind it. Leave space around the edges.
- **Topic colours** for the background and circle:

  | Topic            | Background | Circle    |
  | ---------------- | ---------- | --------- |
  | Singlish         | `#FFF1F2`  | `#FECDD3` |
  | Hawker & Food    | `#FFFBEB`  | `#FDE68A` |
  | Workplace        | `#EEF2FF`  | `#C7D2FE` |
  | Public Etiquette | `#F0FDF4`  | `#BBF7D0` |
  | Festivals        | `#FFF7ED`  | `#FED7AA` |
  | Getting Around   | `#F0F9FF`  | `#BAE6FD` |

- **People** are simple and faceless, with a range of skin tones and everyday clothes. Never use costume, caricature or a stereotype to say where someone is from.
- **Text in the picture** only when it is the point (a sign, a speech bubble), short and spelled exactly. Image generators often misspell, so check every word.
- **Accuracy over decoration.** Show the real thing as it looks in Singapore (an HDB block, a hawker centre tray rack), and have someone other than the author check it before it goes in, as for the lesson text.

### A prompt to start from

> Flat vector illustration, 4:3. [Subject, e.g. "two glass cups of kopi on saucers on a round white marble kopitiam table, steam rising"]. Solid colours, no outlines, no gradients, no texture, soft rounded shapes. Plain [background colour] background with a large soft [circle colour] circle behind the subject. Centred with generous space around it. No text. Any people are simple and faceless, with no exaggerated features.

Generate a few, pick the clearest, and check every detail is right for Singapore.

## Audio

- **Short**: one phrase per card, under 20 seconds (over that is flagged). MP3 or M4A.
- **Real speech** where possible: a Singaporean saying the phrase naturally beats any synthetic voice. Record somewhere quiet, close to the phone.
- **Always write the transcript** in the lesson file, spelled the way the lesson spells it.
- The placeholder clips were made with the `en-SG-LunaNeural` and `en-SG-WayneNeural` voices of Microsoft's text-to-speech (`pip install edge-tts`; `edge-tts --voice en-SG-LunaNeural --text "..." --write-media clip.mp3`).
