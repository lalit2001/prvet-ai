package cmd

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/spf13/cobra"
)

type DependencyStatus struct {
	Status string `json:"status"`
	Error  string `json:"error,omitempty"`
}

type ReadyzResponse map[string]DependencyStatus

func doctorCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "doctor",
		Short: "Probe DB, queue, storage, LLM, forge auth",
		RunE: func(cmd *cobra.Command, args []string) error {
			// 1. Resolve API URL
			apiUrl := os.Getenv("CRV_API_URL")
			if apiUrl == "" {
				apiUrl = getEnvVarFromLocalDotenv("API_URL")
			}
			if apiUrl == "" {
				apiUrl = "http://localhost:8080"
			}
			apiUrl = strings.TrimSuffix(apiUrl, "/")

			fmt.Printf("Probing Sentry Review API at %s...\n\n", apiUrl)

			// 2. Fetch /readyz endpoint
			client := &http.Client{Timeout: 8 * time.Second}
			resp, err := client.Get(apiUrl + "/api/v1/readyz")
			if err != nil {
				fmt.Printf("\033[31m[FAIL]\033[0m API server is unreachable at %s: %v\n", apiUrl, err)
				fmt.Println("Ensure the API container/server is running (`docker compose up` or equivalent).")
				os.Exit(1)
			}
			defer resp.Body.Close()

			body, err := io.ReadAll(resp.Body)
			if err != nil {
				return fmt.Errorf("failed to read response: %w", err)
			}

			// 3. Parse and display checks
			var checks ReadyzResponse
			if err := json.Unmarshal(body, &checks); err != nil {
				// FastAPI might have returned a detail message on 503
				type ErrorDetail struct {
					Detail ReadyzResponse `json:"detail"`
				}
				var errDetail ErrorDetail
				if errJson := json.Unmarshal(body, &errDetail); errJson == nil && len(errDetail.Detail) > 0 {
					checks = errDetail.Detail
				} else {
					fmt.Printf("\033[31m[FAIL]\033[0m Unexpected API response (status %d): %s\n", resp.StatusCode, string(body))
					os.Exit(1)
				}
			}

			allPassed := true
			for component, details := range checks {
				if details.Status == "ok" {
					fmt.Printf("\033[32m[ OK ]\033[0m %-8s : Online and healthy\n", component)
				} else {
					allPassed = false
					fmt.Printf("\033[31m[FAIL]\033[0m %-8s : Offline / Error: %s\n", component, details.Error)
				}
			}

			if !allPassed {
				fmt.Println("\nSome backend services failed health probes. Check logs for details.")
				os.Exit(1)
			}

			fmt.Println("\n\033[32mAll Sentry Review dependency systems are online and healthy!\033[0m")
			return nil
		},
	}
}

func getEnvVarFromLocalDotenv(key string) string {
	data, err := os.ReadFile(".env")
	if err != nil {
		return ""
	}
	lines := strings.Split(string(data), "\n")
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if strings.HasPrefix(line, "#") || !strings.Contains(line, "=") {
			continue
		}
		parts := strings.SplitN(line, "=", 2)
		if strings.TrimSpace(parts[0]) == key {
			val := strings.TrimSpace(parts[1])
			val = strings.Trim(val, `"'`)
			return val
		}
	}
	return ""
}
