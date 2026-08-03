package cmd

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"strings"
	"time"

	"github.com/spf13/cobra"
)

type GateResponse struct {
	Passed bool   `json:"passed"`
	Reason string `json:"reason"`
}

func gateCmd() *cobra.Command {
	c := &cobra.Command{
		Use:   "gate",
		Short: "CI-side gate helpers",
	}
	c.AddCommand(gateCheckCmd())
	return c
}

func gateCheckCmd() *cobra.Command {
	var pr int
	var repo string
	c := &cobra.Command{
		Use:   "check",
		Short: "Exit 0 if the PR gate passes; exit 1 otherwise. For CI.",
		RunE: func(cmd *cobra.Command, args []string) error {
			// 1. Resolve repository name
			if repo == "" {
				repo = detectGitRepo()
			}
			if repo == "" {
				fmt.Fprintln(os.Stderr, "Error: Could not auto-detect git repository. Please provide the --repo flag (e.g. --repo owner/name)")
				os.Exit(2)
			}

			// 2. Resolve API URL
			apiUrl := os.Getenv("CRV_API_URL")
			if apiUrl == "" {
				apiUrl = getEnvVarFromLocalDotenv("API_URL")
			}
			if apiUrl == "" {
				apiUrl = "http://localhost:8080"
			}
			apiUrl = strings.TrimSuffix(apiUrl, "/")

			fmt.Fprintf(os.Stderr, "Checking gate status for %s PR #%d at %s...\n", repo, pr, apiUrl)

			// 3. Query gate check API
			client := &http.Client{Timeout: 10 * time.Second}
			resp, err := client.Get(fmt.Sprintf("%s/api/v1/repos/%s/prs/%d/gate", apiUrl, repo, pr))
			if err != nil {
				fmt.Fprintf(os.Stderr, "Error: API gateway unreachable: %v\n", err)
				os.Exit(2)
			}
			defer resp.Body.Close()

			body, err := io.ReadAll(resp.Body)
			if err != nil {
				fmt.Fprintf(os.Stderr, "Error: Failed to read response body: %v\n", err)
				os.Exit(2)
			}

			if resp.StatusCode != http.StatusOK {
				fmt.Fprintf(os.Stderr, "Error: API returned status %d: %s\n", resp.StatusCode, string(body))
				os.Exit(2)
			}

			var gate GateResponse
			if err := json.Unmarshal(body, &gate); err != nil {
				fmt.Fprintf(os.Stderr, "Error: Failed to parse gate response JSON: %v\n", err)
				os.Exit(2)
			}

			// 4. Output and exit code
			if gate.Passed {
				fmt.Printf("\033[32m[ PASS ]\033[0m %s\n", gate.Reason)
				os.Exit(0)
			} else {
				fmt.Printf("\033[31m[ FAIL ]\033[0m %s\n", gate.Reason)
				os.Exit(1)
			}

			return nil
		},
	}
	c.Flags().IntVar(&pr, "pr", 0, "pull request number")
	c.Flags().StringVar(&repo, "repo", "", "repository identifier (e.g. owner/repo)")
	_ = c.MarkFlagRequired("pr")
	return c
}

func detectGitRepo() string {
	cmd := exec.Command("git", "config", "--get", "remote.origin.url")
	out, err := cmd.Output()
	if err != nil {
		return ""
	}
	url := strings.TrimSpace(string(out))
	url = strings.TrimSuffix(url, ".git")

	// Handle SSH format: git@github.com:owner/repo
	parts := strings.Split(url, ":")
	if len(parts) > 1 {
		url = parts[len(parts)-1]
	}

	// Handle HTTPS format: https://github.com/owner/repo
	parts = strings.Split(url, "/")
	if len(parts) >= 2 {
		return parts[len(parts)-2] + "/" + parts[len(parts)-1]
	}
	return ""
}
