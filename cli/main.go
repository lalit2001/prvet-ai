// crv — Sentry Review deployment helper.
// This binary is deploy-only. Repos, LLMs, rules, thresholds, reports:
// all in the web UI, never here. See plan.md §C5.
package main

import (
	"fmt"
	"os"

	"github.com/sentry-review/crv/cmd"
)

func main() {
	if err := cmd.Root().Execute(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
