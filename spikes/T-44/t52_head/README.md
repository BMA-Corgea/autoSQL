# T-52 head, frozen for the quiet re-time

`compile.py` and `runtime.sql` are byte copies of `compiler/compile.py` and `runtime/runtime.sql` at
`dc088f7` (branch feat/T-44-faster-compiled-path): the SHIPPING CANDIDATE after main (T-60, T-61,
T-63) was merged in. bench_t44.py times them as the REPORTED arm `C_t52`, beside the pre-registered
candidate `C_both`, which the verdict reads on. For the invented widget the two emit byte-identical SQL
(no `==`/`!=`), and the runtime functions on that path are unchanged. Do not edit; re-copy from git.
