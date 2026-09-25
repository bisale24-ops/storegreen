# Short submission fields

**Project title**
StoreGreen

**Short description (one line)**
Know why the store will reject your Android build — before the store does.

**Tags**
Android · release engineering · developer tooling · Amazon Appstore · Google Play ·
static analysis · CI · Python · IBM Bob 2.0

**Demo application platform**
Web (static report pages) + command-line tool

**Application URL**
https://bisale24-ops.github.io/storegreen/

**Public code repository**
https://github.com/bisale24-ops/storegreen

**What a judge can do in two minutes**
```
git clone https://github.com/bisale24-ops/storegreen && cd storegreen
./run.sh --repo fixtures/tipjar-amazon     # nothing to install
./run.sh --aab fixtures/tipjar-amazon.aab  # the rejection, reproduced
./check.sh                                 # 183 tests on 3.9 and 3.13
```
