"""StoreGreen — the submission video.

    ~/.venvs/video/bin/python ~/Desktop/KHLab/hack-nation/kit/video/render.py \
        video/script.py --length-only --max-seconds 170

Rules that shape it: three minutes maximum, and **at least ninety seconds must show the solution in
action on screen**. The `clip:` scenes are real screen recordings and the renderer reports what
share of the running time they are, so the floor is measured, not hoped for.

The clips in video/clips/ are one-second placeholders until the real recordings replace them; the
words are final and their timing is measured with real speech.
"""
VOICE = "en-US-AndrewNeural"

SCENES = [
    ("card:problem",
     "Eleven September. Amazon rejects our Android app: in-app purchase displays an error. On the "
     "test phone everything worked. Two days and two extra builds, for one missing file."),

    ("clip:scan",
     "StoreGreen reads an Android project the way a store reviewer would, before you upload. It "
     "merges the manifests the way Gradle would — main, then flavour, then build type — reads the "
     "versions out of the build files or the version catalogue, and answers in under a second. "
     "Every line names the file and the line number that caused it, so nothing has to be taken on "
     "trust."),

    ("clip:report",
     "The report is one offline page with no network in it at all. Findings first, then what could "
     "not be decided and why, then what passed. That last part matters: a report that only lists "
     "problems cannot be told apart from one that failed to run."),

    ("clip:bundles",
     "And it reads what actually shipped. Four of our own bundles, on sale today. Fifteen native "
     "libraries, and one is not aligned for sixteen kilobyte pages, so that app cannot be updated "
     "on Play after February. In another, Google Play's billing library is riding inside an Amazon "
     "build — the permission in the manifest and the classes in the dex file. We did not know "
     "either of those."),

    ("clip:fix",
     "Then Bob fixes what is deterministic. The purchase receiver, the queries entry, the keep "
     "rules that stop R eight stripping the SDK. It shows the diff, re-runs the scan, and the "
     "verdict turns green. What it will not do is guess: the purchase key it cannot invent, so it "
     "prints the console path to download it and leaves that one open."),

    ("clip:rejection",
     "Already rejected? Paste the store's e-mail. Bob reads it and points at the rule and the line "
     "that caused it, and says plainly which sentences map to nothing. This is the real e-mail "
     "from our own rejection, and these are the two rules it turned out to be."),

    ("card:refuses",
     "What it refuses to say matters as much. A watch app at target thirty-five is correct, not a "
     "violation. A key missing from a public repository is a secret kept properly. And when it "
     "cannot decide it counts that too, naming the line it gave up on. A tool that cannot say I do "
     "not know will eventually say something false."),

    ("clip:bob",
     "All of it was built inside I B M Bob two point zero. It reviewed the specification before "
     "writing anything and found three contradictions I had left in it, then built the rules and "
     "the fixer — and caught one of its own rules matching a keep line inside a comment."),

    ("card:numbers",
     "And the part that is not a demo. Eighty-three public Android repositories, sixty-nine "
     "blocking findings across forty-five of them, not one crash. A hundred and eighty-three tests, "
     "and thirty-five malformed inputs that have to be survived rather than passed."),

    ("card:end",
     "StoreGreen. Green before you submit. M I T licensed, and the narration in this video is "
     "synthesised — there is no presenter."),
]

CARDS = {
    "numbers": """<h1>What was actually run</h1>
    <table>
      <tr><td>83 public repositories</td><td class=d>found by searching GitHub, not chosen by us</td></tr>
      <tr><td class=no>69 BLOCK findings in 45 of them</td><td class=d>the Play deadline passed on 31 August</td></tr>
      <tr><td>29 undecidable</td><td class=d>said so, with the line it gave up on</td></tr>
      <tr><td class=ok>0 crashes</td><td class=d>a crash is our defect, not their finding</td></tr>
      <tr><td>183 tests · 3.9 and 3.13</td><td class=d>35 malformed inputs survived, not passed</td></tr>
    </table>""",

    "problem": """<h1>Rejected for one missing file</h1>
    <p class=sub>CrewSheet 1.0.0, Amazon Appstore, content policy</p>
    <table>
      <tr><td>submitted</td><td class=d>10 September, 14:38 UTC</td></tr>
      <tr><td>rejected</td><td class=no>11 September, 18:42 UTC</td></tr>
      <tr><td>live, as 1.0.2</td><td class=d>13 September, 15:50 UTC</td></tr>
      <tr><td>cost</td><td class=no>73 hours · 2 extra builds</td></tr>
    </table>
    <p class=foot>The reviewer found it. Nothing in the build did.</p>""",

    "refuses": """<h1>What it refuses to say</h1>
    <table>
      <tr><th>input</th><th>naive verdict</th><th>StoreGreen</th></tr>
      <tr><td>Wear OS app, target 35</td><td class=no>BLOCK</td><td class=ok>correct for its form factor</td></tr>
      <tr><td>no key in a public repo</td><td class=no>BLOCK</td><td class=ok>a secret, kept properly</td></tr>
      <tr><td>targetSdk from an env var</td><td class=no>silent pass</td><td class=d>cannot be determined, build.gradle:2</td></tr>
    </table>
    <p class=foot>Decidability is printed as a number on every run, not claimed in a README.</p>""",

    "end": """<h1>StoreGreen</h1>
    <p class=sub>Green before you submit.</p>
    <p class=big>github.com/bisale24-ops/storegreen</p>
    <p class=foot>MIT licensed · built with IBM Bob 2.0 · the narration in this video is
    synthesised, there is no presenter.</p>""",
}

CLIPS = {
    "scan": "clips/scan.mp4",
    "report": "clips/report.mp4",
    "bundles": "clips/bundles.mp4",
    "fix": "clips/fix.mp4",
    "rejection": "clips/rejection.mp4",
    "bob": "clips/bob.mp4",
}
