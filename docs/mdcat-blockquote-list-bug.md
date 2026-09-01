# Lists inside blockquotes lose the quote bar; wrapped items get one mid-text

## What happens

A list nested in a blockquote renders without the `│` prefix its
surrounding text has, and the continuation line of a wrapped item has a
`│` inserted into the middle of the text.

## Reproducing

```markdown
> quoted text
>
> - one
> - two that is long enough to wrap at the terminal width and keep going
```

```
$ mdcat --columns 50 quoted-list.md

│ quoted text

• one
• two that is long enough to wrap at the
  │ terminal width and keep going
```

Expected: the bullets carry `│` as the paragraph above them does, and no
`│` appears inside the wrapped text.

## Not the alert syntax

The same happens inside a GitHub alert, which is where it tends to be
noticed:

```markdown
> [!TIP]
> tip text
>
> - one
> - two
```

```
│ ◆ TIP
│ tip text

• one
• two
```

## Blockquotes without lists are fine

```markdown
> first para
>
> second para
```

```
│ first para
│ 
│ second para
```

So it appears specific to lists nested inside a blockquote, rather than to
blockquote rendering generally.

## Version

```
mdcat 2.15.0
```
