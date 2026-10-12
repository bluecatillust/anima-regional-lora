# Anima Regional LoRA for Forge Neo

An experimental Forge Neo extension that assigns one Anima LoRA to the left
side of an image and another Anima LoRA to the right side.

[日本語の説明はこちら](#日本語)

> [!WARNING]
> This extension is experimental. Compatibility can depend on the Forge Neo
> version, checkpoint, LoRA, sampler, and other installed extensions.

## How it works

At every denoising step, the extension evaluates the diffusion model twice:

1. with the left LoRA enabled and the right LoRA disabled;
2. with the right LoRA enabled and the left LoRA disabled;
3. then blends the two predictions with a horizontal mask.

Forge Neo core files are not modified. Because the diffusion model is evaluated
twice, generation is usually close to twice as expensive as a normal run.

## Installation

1. Open Forge Neo.
2. Go to **Extensions** > **Install from URL**.
3. Paste this repository's Git URL into **URL for extension's git repository**.
4. Click **Install**.
5. Restart Forge Neo completely.

Manual installation is also possible by cloning the repository into:

```text
<Forge Neo>/extensions/anima-regional-lora
```

## Requirements

- Forge Neo with Anima support.
- Set **Diffusion in Low Bits** to **Automatic (fp16 LoRA)** or another option
  whose name ends in **(fp16 LoRA)**, then reload the checkpoint.
- Include both selected LoRAs in the prompt with normal LoRA tags.

The Forge Neo console should show:

```text
Patch LoRAs on-the-fly: True
```

## Usage

Use both character LoRAs in the prompt as usual, for example:

```text
2girls, character A on the left, character B on the right,
<lora:CharacterA:1.0> <lora:CharacterB:1.0>
```

Then:

1. Expand **Anima Regional LoRA (experimental)** in txt2img.
2. Enable **Enable two-pass Regional LoRA**.
3. Enter the LoRA alias or filename for the left and right regions.
4. Adjust each LoRA strength if needed.
5. Start with the boundary at `0.5` and feather at `0.05`.

Feather guide:

- `0` to `0.03`: clearer separation, but the center seam may be visible.
- `0.05`: a practical starting point.
- `0.08` to `0.15`: softer transition, but character traits may mix near the center.

## Settings reference

| Setting | Meaning | Recommended starting value |
| --- | --- | --- |
| **Enable two-pass Regional LoRA** | Enables the extension. The diffusion model is evaluated once for each side and the two predictions are blended. | On |
| **Left LoRA alias or filename** | LoRA to apply to the left region. Enter the alias or filename registered in Forge Neo. | Left character LoRA |
| **Left strength** | Diffusion-model strength of the left LoRA. `0` disables it, while values above `1.0` emphasize it. | `0.8` to `1.0` |
| **Right LoRA alias or filename** | LoRA to apply to the right region. It must be different from the left LoRA. | Right character LoRA |
| **Right strength** | Diffusion-model strength of the right LoRA. | `0.8` to `1.0` |
| **Left/right boundary** | Horizontal split position as a fraction of image width. Increasing it expands the left region. | `0.50` |
| **Boundary feather** | Width of the soft transition around the boundary as a fraction of image width. | `0.05` |

Boundary examples:

- `0.30`: left 30%, right 70%.
- `0.50`: equal left and right regions.
- `0.70`: left 70%, right 30%.

With boundary `0.50` and feather `0.10`, the predictions are blended across
approximately 45% to 55% of the image width. A smaller feather separates the
characters more clearly but can reveal a seam. A larger feather gives a
smoother transition but can mix character traits near the center.

The prompt LoRA tags load the LoRAs into Forge Neo. The **Left strength** and
**Right strength** controls determine their regional diffusion-model strengths.
Text-encoder-side effects from the prompt tags are not spatially separated.

## Limitations

- Only a horizontal left/right split is currently supported.
- Diffusion-model compute is approximately doubled.
- Text-encoder-side LoRA effects are not spatially masked.
- Results can vary with Forge Neo updates, checkpoints, LoRAs, and samplers.
- Hires.fix and other extensions that wrap or replace the denoiser require
  individual compatibility testing.

## Troubleshooting

### The result looks the same as normal LoRA generation

Confirm that the console says `Patch LoRAs on-the-fly: True`. If it says
`False`, select a **(fp16 LoRA)** option under **Diffusion in Low Bits** and
reload the checkpoint.

### A LoRA is not being separated

Confirm that the LoRA is present in the prompt and that the alias entered in
the extension matches the LoRA name shown by Forge Neo.

### The center boundary is too visible

Increase feather gradually. If traits are mixing too much, reduce feather and
compose the characters farther from the center.

---

## 日本語

Anima用LoRAを画像の左側と右側に分けて適用する、Forge Neo向けの実験的な
拡張機能です。

各デノイズステップで、左LoRAのみを有効にした計算と右LoRAのみを有効にした
計算を行い、その結果を横方向のマスクで合成します。Forge Neo本体のファイルは
変更しません。モデル計算が2回になるため、通常より生成時間とVRAM負荷が増えます。

### インストール

1. Forge Neoの **Extensions** を開きます。
2. **Install from URL** を選びます。
3. **URL for extension's git repository** に、このリポジトリのGit URLを貼り付けます。
4. **Install** を押します。
5. Forge Neoを完全に再起動します。

手動で導入する場合は、次の場所へリポジトリをcloneします。

```text
<Forge Neo>/extensions/anima-regional-lora
```

### 必須設定

- Anima対応のForge Neoを使用してください。
- **Diffusion in Low Bits** を **Automatic (fp16 LoRA)**、または名前の末尾が
  **(fp16 LoRA)** の設定に変更し、チェックポイントを再読み込みしてください。
- 左右で使う両方のLoRAを、通常どおりプロンプトへ記載してください。

Forge Neoのコンソールに次の表示が出ることを確認してください。

```text
Patch LoRAs on-the-fly: True
```

### 使い方

プロンプト例:

```text
2girls, character A on the left, character B on the right,
<lora:CharacterA:1.0> <lora:CharacterB:1.0>
```

1. txt2imgの **Anima Regional LoRA (experimental)** を開きます。
2. **Enable two-pass Regional LoRA** をONにします。
3. 左右それぞれの欄へLoRAの別名またはファイル名を入力します。
4. 必要に応じて左右の強度を調整します。
5. 最初は境界位置 `0.5`、ぼかし幅 `0.05` が目安です。

ぼかし幅を小さくすると左右の分離が明確になり、大きくすると中央が自然に
つながります。ただし、大きすぎると中央付近でキャラクターの特徴が混ざります。

### 設定項目の意味

| 項目 | 意味 | 推奨初期値 |
| --- | --- | --- |
| **Enable two-pass Regional LoRA** | 拡張機能を有効にします。左右のLoRAでモデル計算を1回ずつ行い、その結果を合成します。 | ON |
| **Left LoRA alias or filename** | 画像の左側へ適用するLoRAです。Forge Neoに登録されている別名またはファイル名を入力します。 | 左キャラクターのLoRA名 |
| **Left strength** | 左側LoRAの拡散モデル側の強度です。`0`で無効になり、`1.0`を超えると特徴が強くなります。 | `0.8`～`1.0` |
| **Right LoRA alias or filename** | 画像の右側へ適用するLoRAです。左側とは異なるLoRAを指定します。 | 右キャラクターのLoRA名 |
| **Right strength** | 右側LoRAの拡散モデル側の強度です。 | `0.8`～`1.0` |
| **Left/right boundary** | 画像横幅に対する左右の境界位置です。値を大きくすると左領域が広がります。 | `0.50` |
| **Boundary feather** | 境界をなめらかに混ぜる幅です。画像横幅に対する割合で指定します。 | `0.05` |

**Left/right boundary** の例:

- `0.30`: 左30%、右70%。
- `0.50`: 左右半分ずつ。
- `0.70`: 左70%、右30%。

**Boundary feather** の目安:

- `0`～`0.03`: 左右の分離が明確になりますが、中央に継ぎ目が出やすくなります。
- `0.05`: 標準的な開始値です。
- `0.08`～`0.15`: 境界が自然になりますが、中央付近で特徴が混ざりやすくなります。

境界`0.50`、ぼかし幅`0.10`の場合、おおむね画像横幅の45%～55%が
左右の移行領域になります。

プロンプトの`<lora:...:...>`タグにはLoRAをForge Neoへ読み込ませる役割があり、
設定画面の **Left strength** と **Right strength** が各領域での拡散モデル側の
強度を決めます。テキストエンコーダー側のLoRA効果は領域分割されません。

最初は、プロンプト側と設定画面側を両方`1.0`にし、設定画面側の強度から
調整すると分かりやすくなります。

`Patch LoRAs on-the-fly: False`と表示される場合は、Animaプリセットを選んだ後、
**Diffusion in Low Bits**を **Automatic (fp16 LoRA)** など、名前の末尾が
**(fp16 LoRA)** の設定へ変更し、モデルを再読み込みしてください。

### 制限事項

- 現在は左右分割のみです。
- 拡散モデルの計算量はおおむね2倍になります。
- テキストエンコーダー側のLoRA効果は領域分割されません。
- Forge Neo、モデル、LoRA、サンプラーなどの組み合わせにより結果が変わります。
- Hires.fixやデノイザーを変更する別拡張との併用は、個別の確認が必要です。

## Development

The dependency-free core tests can be run with:

```text
python -m unittest discover -s tests -v
```

