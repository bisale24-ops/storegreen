# AMZ-IAP-06 defect: keep rules cover only the narrow sub-package
# com.amazon.device.iap.** instead of the required com.amazon.**
# The three required lines (-keep class com.amazon.**, -dontwarn com.amazon.**,
# -keepattributes *Annotation*) are absent.
-keep class com.amazon.device.iap.** { *; }
-keep class com.example.tipjar.** { *; }
