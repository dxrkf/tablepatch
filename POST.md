# Arabic launch draft

بنيت TablePatch لتسهيل مراجعة نسخ ملفات CSV: يوضح الصفوف الجديدة والمحذوفة والمعدلة اعتمادًا على عمود فريد، ويتجاهل ضوضاء إعادة ترتيب الصفوف والأعمدة.

ويولّد ملف تغييرات يمكن تطبيقه على نسخة مطابقة من الأصل لإنشاء CSV جديد، مع التحقق من بصمة البيانات ورفض الكتابة فوق الملفات الموجودة.

يعمل محليًا دون مكتبات خارجية، مع تقرير HTML وأمثلة و16 اختبارًا ناجحًا.

https://github.com/dxrkf/tablepatch

#Python #DataEngineering #OpenSource #DeveloperTools

# English launch draft

Introducing TablePatch: a tiny offline Python CLI for key-aware CSV diffs and replayable change sets.

Ignore sorting noise, review added/removed/updated rows, then apply the patch to a matching baseline and verify the reconstructed data fingerprint. Existing files are never overwritten.

Zero dependencies. Includes HTML review, synthetic examples and 16 passing tests.

https://github.com/dxrkf/tablepatch

Attach assets/cover.png and assets/demo-output.png. Review reports before sharing: they include full cell values.
