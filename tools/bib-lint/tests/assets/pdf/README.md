# Pinned conference template sources

These unmodified sources support the PDF acceptance tests. The required source subset is vendored so local and CI template preparation needs no network access. Original archive identities remain provenance; no zip archives, Word documents, compiled PDFs, or publication forms are included.

Every copied file retains its original bytes, including embedded copyright and license notices. Standalone upstream notices are included and checksum-pinned as `notices` in [the template manifest](../../fixtures/pdf/templates.json). `prepare_asset` and `verified_asset` reject changed, missing, unsafe, or symlinked inputs.

These files retain their upstream licensing; the repository's MIT license does not replace those terms.

The manifest also records the exact conference configurations and compiler digest. Asset updates require explicit pin and rendering review; never replace a kit silently.

## neurips

- Official instructions: [https://neurips.cc/Conferences/2026/CallForPapers](https://neurips.cc/Conferences/2026/CallForPapers)
- Original archive: [https://media.neurips.cc/Conferences/NeurIPS2026/Formatting_Instructions_For_NeurIPS_2026.zip](https://media.neurips.cc/Conferences/NeurIPS2026/Formatting_Instructions_For_NeurIPS_2026.zip)
- Original archive SHA-256: `82473931e3ef710fcd3f4a8cd4119b9de32e56825f90f9e5a6d55f2d01b817d9` (20,259 bytes).
- Original archive member root: `./`.
- Resolved archive URL: [https://media.neurips.cc/Conferences/NeurIPS2026/Formatting_Instructions_For_NeurIPS_2026.zip](https://media.neurips.cc/Conferences/NeurIPS2026/Formatting_Instructions_For_NeurIPS_2026.zip).

| Included file | SHA-256 |
| --- | --- |
| [neurips_2026.tex](neurips/neurips_2026.tex) | `cf4cee7991665306d1daaa3985be4feec7f8889d6d072ffa12f99a8e1537d797` |
| [checklist.tex](neurips/checklist.tex) | `780ba13c480f652dcc42e69ed61a752ce0ea270f15d332d4a45b059dabad84f6` |
| [neurips_2026.sty](neurips/neurips_2026.sty) | `c3fc2894e83d2517ca18b66741d6c595986d97957dc08ec08bb2125a7ec4555a` |

## icml

- Official instructions: [https://icml.cc/Conferences/2026/AuthorInstructions](https://icml.cc/Conferences/2026/AuthorInstructions)
- Original archive: [https://media.icml.cc/Conferences/ICML2026/Styles/icml2026.zip](https://media.icml.cc/Conferences/ICML2026/Styles/icml2026.zip)
- Original archive SHA-256: `8b29290f5828e176debb57ea9cc00252502973d55ea561a2f18a7f0a326bfc6c` (228,368 bytes).
- Original archive member root: `./`.
- Resolved archive URL: [https://media.icml.cc/Conferences/ICML2026/Styles/icml2026.zip](https://media.icml.cc/Conferences/ICML2026/Styles/icml2026.zip).

| Included file | SHA-256 |
| --- | --- |
| [algorithm.sty](icml/algorithm.sty) | `93fd0eb31c112eb405833db8f1d7f5d238c7e691b1c05680d7276e68f36d564a` |
| [algorithmic.sty](icml/algorithmic.sty) | `48d18794a5d97c0479a588cc2eac0917992feb9da83acc4631b8f55757d80f9b` |
| [example_paper.tex](icml/example_paper.tex) | `c2ca8140bf255d1ff77d1278eb3eefed4018b4b1e71065b8e1ccbc68b74c8acf` |
| [fancyhdr.sty](icml/fancyhdr.sty) | `9130c52f91087abc6d223164ffa587e207e3257fcbcd069ef09ecb5391043f14` |
| [icml2026.bst](icml/icml2026.bst) | `0ec3d5eb9b02efb7e0b44a32f3775882f42a743d0bdc618f34e6936309b98764` |
| [icml2026.sty](icml/icml2026.sty) | `7cdcf90f6a59c5219e7f15c88f7ed09fcaf598dad91e6cdddc4dc3cb0e397a95` |

## iclr

- Official instructions: [https://iclr.cc/Conferences/2027/AuthorGuidelines](https://iclr.cc/Conferences/2027/AuthorGuidelines)
- Original archive: [https://media.iclr.cc/Conferences/ICLR2027/iclr-2027-style-files.zip](https://media.iclr.cc/Conferences/ICLR2027/iclr-2027-style-files.zip)
- Original archive SHA-256: `0d940dfa9398ae99a18f24a85a8a683f367204b6af6d17d2899e60a67102529e` (39,348 bytes).
- Original archive member root: `iclr2027/`.
- Resolved archive URL: [https://media.iclr.cc/Conferences/ICLR2027/iclr-2027-style-files.zip](https://media.iclr.cc/Conferences/ICLR2027/iclr-2027-style-files.zip).

| Included file | SHA-256 |
| --- | --- |
| [math_commands.tex](iclr/math_commands.tex) | `90473c4d0542070db244cea73ef962d6cddc5b2a746757e6a40ddf5fdfb90ba9` |
| [fancyhdr.sty](iclr/fancyhdr.sty) | `b56ec4434b9f4607529a4b23dc68ad8d4b94f1f631c8cddaf7da78140d53a5ea` |
| [iclr2027_conference.bst](iclr/iclr2027_conference.bst) | `2d67552db7ed38ccfccb5957b52f95656e25c249724761d3cf5f7922ad1844c5` |
| [iclr2027_conference.tex](iclr/iclr2027_conference.tex) | `03e556d6e5593e498fd39f262ec2d184ebfe8693cbf47fb7cea3402d8d5166ac` |
| [natbib.sty](iclr/natbib.sty) | `88bc70c0e48461934cab5b2accef06b74a8b3ac45ad03ccd3f2a6b7e0d6d530d` |
| [iclr2027_conference.sty](iclr/iclr2027_conference.sty) | `797deef41724e93761426ac0cbcca46279a91cc650dd1f0ce76a4f08d2098ea6` |

## aaai

- Official instructions: [https://aaai.org/conference/aaai/aaai-26/main-technical-track-call/](https://aaai.org/conference/aaai/aaai-26/main-technical-track-call/)
- Original archive: [https://aaai.org/authorkit26-1/](https://aaai.org/authorkit26-1/)
- Original archive SHA-256: `d2844ec68a4a9396d749fcca5b5784809617b670863e8d4fecbfb00e444fc3af` (7,024,737 bytes).
- Original archive member root: `AuthorKit26/AnonymousSubmission/LaTeX/`.
- Resolved archive URL: [https://aaai.org/wp-content/uploads/2025/07/AuthorKit26-1.zip](https://aaai.org/wp-content/uploads/2025/07/AuthorKit26-1.zip).

| Included file | SHA-256 |
| --- | --- |
| [aaai2026.bst](aaai/aaai2026.bst) | `ac26e2c66047435c0ed25f21ae36ad42d731cf3d794c4a8b5f05a62141a27294` |
| [anonymous-submission-latex-2026.tex](aaai/anonymous-submission-latex-2026.tex) | `9112a7c5283ef9080e4dd44a3e115b7775be35d3135f33b03d2e482f65c704ee` |
| [aaai2026.sty](aaai/aaai2026.sty) | `6f90c4d7a36f4a038daf187fdd6cec9fe578aba819733b49551574a37feecd35` |

## ijcai

- Official instructions: [https://ijcai.org/authors_kit/](https://ijcai.org/authors_kit/)
- Original archive: [https://ijcai.org/sites/default/files/Guidelines/FormattingGuidelines-IJCAI-27.zip](https://ijcai.org/sites/default/files/Guidelines/FormattingGuidelines-IJCAI-27.zip)
- Original archive SHA-256: `1f829e86070353eb72220864632c4e6c5a6dd160c35380e68de14a242078b663` (65,957 bytes).
- Original archive member root: `./`.
- Resolved archive URL: [https://ijcai.org/sites/default/files/Guidelines/FormattingGuidelines-IJCAI-27.zip](https://ijcai.org/sites/default/files/Guidelines/FormattingGuidelines-IJCAI-27.zip).

| Included file | SHA-256 |
| --- | --- |
| [ijcai27.sty](ijcai/ijcai27.sty) | `cdf7ca9a28c6b1ba60cde0f42019ccea3722838242b69471db572d21f879d3b2` |
| [ijcai27.tex](ijcai/ijcai27.tex) | `e55c680ffad8213b91da9091a5238e8e0281cc019b7f7b29654776f14d85ab05` |
| [named.bst](ijcai/named.bst) | `72c53a0febca9745a9a6febdc1e49327d2b6ac4f161e1d7a210dd47e5f5dda40` |

## aistats

- Official instructions: [https://virtual.aistats.org/Conferences/2026/CallForPapers](https://virtual.aistats.org/Conferences/2026/CallForPapers)
- Original archive: [https://aistats.org/aistats2026/AISTATS2026PaperPack.zip](https://aistats.org/aistats2026/AISTATS2026PaperPack.zip)
- Original archive SHA-256: `7eb3c52735e16446e4b9f59de579599d7ca5714ca0412e0def1c32003882565c` (266,185 bytes).
- Original archive member root: `AISTATS2026PaperPack/`.
- Resolved archive URL: [https://aistats.org/aistats2026/AISTATS2026PaperPack.zip](https://aistats.org/aistats2026/AISTATS2026PaperPack.zip).

| Included file | SHA-256 |
| --- | --- |
| [supplement.tex](aistats/supplement.tex) | `5c553253a0f75988893e654af6416fd0e2d0c4d5216c576cd37c4fd104f1851b` |
| [sample_paper.tex](aistats/sample_paper.tex) | `a78429d0a5cbe45469319776275f5ac5f6a26305ac25d3d5852d39eda3fda849` |
| [fancyhdr.sty](aistats/fancyhdr.sty) | `b56ec4434b9f4607529a4b23dc68ad8d4b94f1f631c8cddaf7da78140d53a5ea` |
| [aistats2026.sty](aistats/aistats2026.sty) | `4c95c0442152f17d460c0402080efd56334c1265bc0d809460eb2e23ee17696d` |

## acl

- Official instructions: [https://github.com/acl-org/acl-style-files](https://github.com/acl-org/acl-style-files)
- Original archive: [https://codeload.github.com/acl-org/acl-style-files/zip/d5adc823ff0f80f98c80405ca0ab66c68e684409](https://codeload.github.com/acl-org/acl-style-files/zip/d5adc823ff0f80f98c80405ca0ab66c68e684409)
- Original archive SHA-256: `35b158b724d04435a657ab214fe4da5f2b57808fc15ca0f24b751bc07b1d1c73` (37,969 bytes).
- Original archive member root: `acl-style-files-d5adc823ff0f80f98c80405ca0ab66c68e684409/`.
- Resolved archive URL: [https://codeload.github.com/acl-org/acl-style-files/zip/d5adc823ff0f80f98c80405ca0ab66c68e684409](https://codeload.github.com/acl-org/acl-style-files/zip/d5adc823ff0f80f98c80405ca0ab66c68e684409).
- Upstream revision: `d5adc823ff0f80f98c80405ca0ab66c68e684409`.

| Included file | SHA-256 |
| --- | --- |
| [acl.sty](acl/acl.sty) | `19dfeddc2c0e448f3926a0bef048a9db3f3611b46265b760caabd7ada4f361de` |
| [acl_latex.tex](acl/acl_latex.tex) | `339c9ee9705c1767d44ef24b85365c0bb8619ecc3fcf66172bf1356292389614` |
| [acl_lualatex.tex](acl/acl_lualatex.tex) | `0d9987ba833331a996f9abcd1a03eebba7d7ae331145793e7ddb6b5ae8db27b3` |
| [acl_natbib.bst](acl/acl_natbib.bst) | `6fbb306202290f4b68e74ac1460a8b27398500cb6dfeb4492e74c457eae7cd1e` |
| [README.md](acl/README.md) | `f5e4fe5096e8bc045b586a2351409f29ce6d55e0268a434602a06011f571d882` |

## cvpr

- Official instructions: [https://github.com/cvpr-org/author-kit](https://github.com/cvpr-org/author-kit)
- Original archive: [https://codeload.github.com/cvpr-org/author-kit/zip/a2369342011145be8c85e5ad21a9b61f9fa53473](https://codeload.github.com/cvpr-org/author-kit/zip/a2369342011145be8c85e5ad21a9b61f9fa53473)
- Original archive SHA-256: `5d8e151fc9abdd6e641bc30571c40b762a1998f1b8c441ec25d9a5f3deb8d303` (31,515 bytes).
- Original archive member root: `author-kit-a2369342011145be8c85e5ad21a9b61f9fa53473/`.
- Resolved archive URL: [https://codeload.github.com/cvpr-org/author-kit/zip/a2369342011145be8c85e5ad21a9b61f9fa53473](https://codeload.github.com/cvpr-org/author-kit/zip/a2369342011145be8c85e5ad21a9b61f9fa53473).
- Upstream revision: `a2369342011145be8c85e5ad21a9b61f9fa53473`.

| Included file | SHA-256 |
| --- | --- |
| [cvpr.sty](cvpr/cvpr.sty) | `ae8e51adc7270b118833b2092310ca1151a19fab0c09b1ab35a485ac4004ac0f` |
| [fig/teaser.tex](cvpr/fig/teaser.tex) | `17a5bd63167d6fab7c2ad2c678b9522fac199bee19b782018ceefffed32ac3ca` |
| [ieeenat_fullname.bst](cvpr/ieeenat_fullname.bst) | `e38e6166bd7b1e6d23a1b79dcdb55c656e4fcdbe91bdf6b50d827e6b5d1aacfc` |
| [main.tex](cvpr/main.tex) | `391ada680eec864708cfbca25661ba47d95996c24fa349c9133afc9f3a222f96` |
| [preamble.tex](cvpr/preamble.tex) | `080e0bae5ff30626292192ee2b4d1afca432ed2d2c939486c1bb37856166f8c1` |
| [rebuttal.tex](cvpr/rebuttal.tex) | `ef185377321633a2511716a66533cb968eb75856e8f6b6dead61a4419ffcedac` |
| [sec/0_abstract.tex](cvpr/sec/0_abstract.tex) | `ac059e9cb8595bab8f7795d088d71e321ee46e8397d5cfb56957107d43c868ed` |
| [sec/1_intro.tex](cvpr/sec/1_intro.tex) | `3a7e9d973dad94c7f6d101e7e1eb3bad8edb80e6335a6f4014e8a2f40a3e8175` |
| [sec/2_formatting.tex](cvpr/sec/2_formatting.tex) | `72b0eb3b2b255c0dd67f3ee295f5e52f3bbbe4a2aa29c7dd790c69a5954a5994` |
| [sec/3_finalcopy.tex](cvpr/sec/3_finalcopy.tex) | `ae261b3daaff50cf609bb3ca7dfd030bb1e835fd85aa4fda45cdaf53cc35cc1a` |
| [sec/X_suppl.tex](cvpr/sec/X_suppl.tex) | `594291f94cf3b925908dc127a93f3525c1998e96abf37a14f69d6077a7e58bd7` |
| [README.md](cvpr/README.md) | `82c198ab5fb54cc77dd476206bb81287928e757753611e469a20f7a7e598c1a4` |

## eccv

- Official instructions: [https://eccv.ecva.net/Conferences/2026/SubmissionPolicies](https://eccv.ecva.net/Conferences/2026/SubmissionPolicies)
- Original archive: [https://codeload.github.com/paolo-favaro/paper-template/zip/da8c09c40239d5665757527e77388f4716a6564a](https://codeload.github.com/paolo-favaro/paper-template/zip/da8c09c40239d5665757527e77388f4716a6564a)
- Original archive SHA-256: `1c1c8a188decf1f1adfccadb0585ccc95cef17f7ef846f4a5291ba1c5407b4a1` (657,190 bytes).
- Original archive member root: `paper-template-da8c09c40239d5665757527e77388f4716a6564a/`.
- Resolved archive URL: [https://codeload.github.com/paolo-favaro/paper-template/zip/da8c09c40239d5665757527e77388f4716a6564a](https://codeload.github.com/paolo-favaro/paper-template/zip/da8c09c40239d5665757527e77388f4716a6564a).
- Upstream revision: `da8c09c40239d5665757527e77388f4716a6564a`.

| Included file | SHA-256 |
| --- | --- |
| [eccv.sty](eccv/eccv.sty) | `07785f87dd4741a761e5064d6752e59dbca308b7999de35df983e70dc0a33d80` |
| [eccvabbrv.sty](eccv/eccvabbrv.sty) | `1c9aba814d428d8d90bfdfde53e3ad8edc9f1db0e5f12e052f713fd5b38e483f` |
| [llncs.cls](eccv/llncs.cls) | `8152fe7afa929cbd3f3679d6f7c1d562525414ed9c5940a69e86cd923416cb2b` |
| [main.tex](eccv/main.tex) | `ac91a7eb6d0991301bca2b1879177495f176dfc7737c77f5d1079852f33fd7e9` |
| [splncs04.bst](eccv/splncs04.bst) | `564cb6156e2400e3755a58bed9caabccb3067dd37a48efcb66851a56d4475c4c` |
| [LICENSE](eccv/LICENSE) | `82d8789febf72672fc2c6ce0b3f4b6ae17bad4b7c195b436179d8b71529c81a6` |
| [README.md](eccv/README.md) | `2892b0207b3c6bb4ebd45efbe75cb25da74f9163871b76add5d1e05870654491` |
| [lncs_readme.txt](eccv/lncs_readme.txt) | `7dbe59c722450e662ff2ffa248fb4338ea3bbcdaabc3ad6d648be7054aa062d1` |

