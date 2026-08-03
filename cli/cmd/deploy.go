package cmd

import (
	"fmt"
	"os"
	"os/exec"

	"github.com/spf13/cobra"
)

func deployCmd() *cobra.Command {
	var target string
	c := &cobra.Command{
		Use:   "deploy",
		Short: "Provision & bring up the stack on the chosen target",
		RunE: func(cmd *cobra.Command, args []string) error {
			fmt.Printf("Deploying Sentry Review stack to target: %s...\n\n", target)

			switch target {
			case "compose":
				return runShellCmd("docker", "compose", "--project-directory", "deploy/compose", "up", "-d")
			case "aws":
				err := runShellCmd("terraform", "-chdir=deploy/terraform/modules/aws/", "init")
				if err != nil {
					return err
				}
				return runShellCmd("terraform", "-chdir=deploy/terraform/modules/aws/", "apply", "-auto-approve")
			case "azure":
				err := runShellCmd("terraform", "-chdir=deploy/terraform/modules/azure/", "init")
				if err != nil {
					return err
				}
				return runShellCmd("terraform", "-chdir=deploy/terraform/modules/azure/", "apply", "-auto-approve")
			case "k8s":
				return runShellCmd("helm", "upgrade", "--install", "crv", "deploy/helm/codereview", "--namespace", "crv", "--create-namespace")
			default:
				return fmt.Errorf("unknown target: %s", target)
			}
		},
	}
	c.Flags().StringVar(&target, "target", "compose", "compose|aws|azure|k8s")
	return c
}

func destroyCmd() *cobra.Command {
	var target string
	c := &cobra.Command{
		Use:   "destroy",
		Short: "Tear down the deployed stack",
		RunE: func(cmd *cobra.Command, args []string) error {
			fmt.Printf("Destroying Sentry Review stack on target: %s...\n\n", target)

			switch target {
			case "compose":
				return runShellCmd("docker", "compose", "--project-directory", "deploy/compose", "down", "-v")
			case "aws":
				return runShellCmd("terraform", "-chdir=deploy/terraform/modules/aws/", "destroy", "-auto-approve")
			case "azure":
				return runShellCmd("terraform", "-chdir=deploy/terraform/modules/azure/", "destroy", "-auto-approve")
			case "k8s":
				return runShellCmd("helm", "uninstall", "crv", "--namespace", "crv")
			default:
				return fmt.Errorf("unknown target: %s", target)
			}
		},
	}
	c.Flags().StringVar(&target, "target", "compose", "compose|aws|azure|k8s")
	return c
}

func runShellCmd(command string, args ...string) error {
	cmd := exec.Command(command, args...)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	return cmd.Run()
}
