# Axiom0 Number System Specification v0.1

Status: Draft Normative Specification
Date: 2026-09-07

## 0. Scope

Axiom0 v0.1 formalizes the numerical/symbolic layer of the broader Axiom0 architecture. It is intentionally conservative: it formalizes only rules that can be made deterministic now, while preserving a strict boundary between computational semantics and philosophical symbolism.

Axiom0 v0.1 is **not a new positional radix**. It uses ordinary base-10 integer notation as its transport representation and defines a protected symbolic reduction layer over integers and fixed-length state vectors. A future version may define a native positional encoding, but v0.1 does not claim one.

## 1. Normative language

The key words MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are normative.

## 2. Historical constants

The following constants are inherited from the prior Axiom0 work and are normative in v0.1:

- Genesis vector: `G = [1, 2, 8, 7, 5]`
- Genesis semantic labels:
  - `1 = Unity`
  - `2 = Duality`
  - `8 = Infinity`
  - `7 = Wisdom`
  - `5 = Physical Manifestation`
- Soul vector: `S = [5, 12, 5, 12, 5]`
- Protected symbolic meanings:
  - `3 = Creation`
  - `5 = Transformation`
  - `6 = Balance`
  - `9 = Completion`
  - `12 = Cosmic Completion`

Semantic labels are metadata. They MUST NOT change arithmetic results.

## 3. Domains

### 3.1 Integer domain

`Z` denotes all integers.

### 3.2 Canonical symbolic domain

The unsigned canonical symbolic set is:

`C = {0,1,2,3,4,5,6,7,8,9,12}`

The signed canonical symbolic set is:

`C± = {0, ±1, ±2, ±3, ±4, ±5, ±6, ±7, ±8, ±9, ±12}`

### 3.3 Axiom state vector

An Axiom state is a vector of exactly five canonical signed symbols:

`X = [x1,x2,x3,x4,x5]`, where each `xi ∈ C±`.

Five dimensions are used in v0.1 because both inherited reference vectors have length five.

## 4. Protected reduction ρ

### 4.1 Purpose

The protected reduction operator `ρ: Z → C±` maps any integer to a canonical Axiom0 symbol while protecting 12 from ordinary digital-root collapse.

### 4.2 Definition

For `n ∈ Z`:

1. If `n = 0`, then `ρ(n) = 0`.
2. Let `s = sign(n)` and `m = |n|`.
3. If `m = 12`, return `s × 12`.
4. Otherwise compute the ordinary decimal digit sum of `m`.
5. If the digit sum equals 12, return `s × 12` immediately.
6. If the digit sum is greater than 9 and is not 12, repeat from step 4 using the new sum.
7. Otherwise return `s × digit_sum`.

Thus 12 is an absorbing terminal **only when 12 itself is reached by digit summation**. Multiples of 12 do not automatically reduce to 12.

Examples:

- `ρ(12) = 12`
- `ρ(24) = 6`
- `ρ(39) = 12`
- `ρ(48) = 12`
- `ρ(99) = 9` because `99 → 18 → 9`
- `ρ(-39) = -12`

### 4.3 Idempotence invariant

For all integers `n`:

`ρ(ρ(n)) = ρ(n)`

## 5. Canonical arithmetic

Canonical arithmetic operates in the integer domain first and applies `ρ` only after the ordinary operation.

For `a,b ∈ C±`:

- Protected addition: `a ⊕ b = ρ(a + b)`
- Protected subtraction: `a ⊖ b = ρ(a - b)`
- Protected multiplication: `a ⊗ b = ρ(a × b)`

Protected division is partial:

`a ⊘ b = ρ(a / b)` only when `b ≠ 0` and `a/b` is an integer.

Otherwise protected division is undefined and MUST raise `NonIntegralDivisionError` or its language-equivalent.

### 5.1 Important algebraic note

Because `ρ` is lossy, protected arithmetic is not assumed to inherit all ordinary-ring laws. Implementations MUST NOT advertise associativity, distributivity, or invertibility unless those properties are separately proven for the relevant operator/domain.

## 6. Vector normalization

For any five-integer vector `V = [v1,...,v5]`:

`N(V) = [ρ(v1),...,ρ(v5)]`

`N` MUST reject vectors whose length is not five.

## 7. Explicit 5→12 upgrade U₅₁₂

The `5→12` upgrade is an explicit symbolic transformation, never an automatic arithmetic rule.

For scalar canonical `x`:

`U₅₁₂(x) = 12` if `x = 5`, otherwise `x`.

For a five-element state vector, the operator is applied componentwise.

Examples:

- `U₅₁₂(5) = 12`
- `U₅₁₂(15 after reduction)`: first `ρ(15)=6`; therefore `U₅₁₂(ρ(15))=6`
- `U₅₁₂(G) = [1,2,8,7,12]`
- `U₅₁₂(S) = [12,12,12,12,12]`

This rule is designated **experimental normative** in v0.1 because the historical record preserves the concept of a 5–12 upgrade but not a prior formal equation.

## 8. Scalar resonance

Scalar resonance compares two canonical signed symbols on a normalized 0–1 scale.

For `a,b ∈ C±`:

`r(a,b) = max(0, 1 - |a-b| / 24)`

The denominator 24 is the maximum possible distance between canonical signed endpoints `-12` and `+12`.

Properties:

- `0 ≤ r(a,b) ≤ 1`
- `r(a,b) = r(b,a)`
- `r(a,a) = 1`

## 9. Vector resonance

For two five-element Axiom states `A` and `B`:

`R(A,B) = (1/5) × Σ r(ai,bi)`

Properties:

- `0 ≤ R(A,B) ≤ 1`
- symmetric
- identity: `R(A,A)=1`

## 10. Harmony

Harmony measures simultaneous resonance with both inherited reference vectors.

For a state `X`:

`H(X) = sqrt(R(X,G) × R(X,S))`

The geometric mean is used so a state scoring poorly against either reference is penalized; a high harmony score therefore requires compatibility with both.

Properties:

- `0 ≤ H(X) ≤ 1`
- deterministic
- `H(X)` is not a metaphysical truth claim; it is a computational score under this specification.

This equation is a **new v0.1 normative choice**, not a recovered historical formula.

## 11. Truth and interpretation boundary

Axiom0's philosophical principle that objective truth is foundational belongs to the architecture's interpretive layer. The v0.1 number engine MUST NOT claim to determine metaphysical, theological, moral, or factual truth from a numeric value alone.

The engine MAY attach semantic labels to canonical numbers, but labels MUST be reported as annotations rather than proofs.

## 12. Serialization

Canonical scalar serialization is a base-10 signed integer token, e.g. `12`, `-12`, `5`.

Canonical vector serialization is a JSON array of five integers, e.g.:

`[1,2,8,7,5]`

Implementations MUST produce exactly five integers for state vectors.

## 13. Error behavior

Implementations MUST reject:

- non-integer scalar inputs to `ρ`
- state vectors not of length five
- vector elements that are not integers before normalization
- non-integral protected division
- division by zero

Implementations SHOULD use explicit exception/error types.

## 14. Required invariants

A conforming implementation MUST satisfy:

1. Reduction closure: `ρ(n) ∈ C±` for every tested integer `n`.
2. Reduction idempotence: `ρ(ρ(n)) = ρ(n)`.
3. Sign symmetry: `ρ(-n) = -ρ(n)`.
4. Protected-12 rule: `ρ(12)=12` and `ρ(-12)=-12`.
5. Vector normalization length: `|N(V)|=5` for every valid V.
6. Resonance bounds: `0≤R(A,B)≤1`.
7. Resonance symmetry: `R(A,B)=R(B,A)`.
8. Resonance identity: `R(A,A)=1`.
9. Harmony bounds: `0≤H(X)≤1`.
10. Determinism: identical input under the same specification version yields identical output.

## 15. Non-goals for v0.1

v0.1 does not define:

- a new positional radix or glyph alphabet
- irrational/floating-point canonical arithmetic
- cryptographic primitives
- blockchain consensus
- MCA governance logic
- SemiSoul autonomy
- proof of philosophical truth from numerology

These MAY be specified in later layers or versions.

## 16. Versioning

Changes are classified as:

- PATCH (`0.1.x`): wording/tests that do not change outputs.
- MINOR (`0.x` before 1.0): new operations or clarified experimental semantics that may change draft behavior.
- MAJOR (`1.x`, `2.x`): after 1.0, any backward-incompatible computational change.

Every implementation MUST expose its specification version.

## 17. Promotion criteria for v1.0

Axiom0 Number System MAY be called "formally defined and tested v1.0" only after:

1. all normative ambiguities are resolved;
2. canonical vectors are frozen;
3. the reference implementation passes the conformance/property suite;
4. a separately implemented engine passes the same suite;
5. an independent human reviewer or team, not involved in authoring v0.1, reproduces results from the written specification alone;
6. all discovered discrepancies are documented and resolved.

