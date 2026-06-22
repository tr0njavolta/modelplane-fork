// Copyright 2026 The Modelplane Authors.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// Command oracle is a parity oracle for the quantity, semver, and cel Python
// modules. It runs inputs through the real Kubernetes code those modules
// reimplement and prints what upstream actually does:
//
//   - parse mode uses k8s.io/apimachinery's resource.ParseQuantity (the oracle
//     for quantity.py's parsing, canonical form, and int64 saturation);
//   - match mode uses k8s.io/dynamic-resource-allocation/cel - the exact CEL env
//     a real DRA device selector compiles against, carrying the quantity() and
//     semver() libraries and the typed `device` input (the oracle for cel.py,
//     and for the quantity()/semver() CEL surface). It evaluates each selector
//     against a device, optionally one supplied as JSON.
//
// It is a DEVELOPER TOOL, not part of the test suite. The committed Python
// tests (test_quantity.py, test_semver.py, test_cel.py) pin upstream-correct
// answers as a regression guard; this oracle is how you DISCOVER those answers
// when you change one of the modules or bump the target Kubernetes version.
// Run it, then transcribe its answers into the test tables.
//
// The parity target is the Kubernetes version pinned in go.mod (see
// k8s.io/apimachinery, k8s.io/apiserver, and k8s.io/dynamic-resource-allocation).
// Bump those to retarget.
//
// Usage (Go is not in the dev shell - pull it in ad hoc):
//
//	cd functions/compose-model-deployment/tests/oracle
//
//	# Quantity parsing: is each string a valid resource.Quantity, and what is
//	# its canonical form? One quantity string per line on stdin.
//	printf '256E\n10Ei\n8Ei\nMi\n' | nix shell nixpkgs#go --command go run . parse
//
//	# Selector evaluation, no device: deviceless quantity()/semver() checks and
//	# domain-presence return a real bool; an expression reading a concrete
//	# attribute/capacity value gets eval-error (the value is unbound).
//	printf 'isQuantity("256E")\nsign(quantity("50k")) == 1\n' | \
//	  nix shell nixpkgs#go --command go run . match
//
//	# Selector evaluation against a device (leading JSON arg): attribute and
//	# capacity reads now return real bools.
//	DEV='{"driver":"gpu.nvidia.com","attributes":{"architecture":{"string":"Hopper"}},"capacity":{"memory":{"value":"141Gi"}}}'
//	printf 'device.attributes["gpu.nvidia.com"].architecture == "Hopper"\n' | \
//	  nix shell nixpkgs#go --command go run . match "$DEV"
//
// Inputs may also be passed as arguments instead of on stdin:
//
//	nix shell nixpkgs#go --command go run . parse 256E 10Ei 8Ei
package main

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"strings"

	resourceapi "k8s.io/api/resource/v1beta1"
	"k8s.io/apimachinery/pkg/api/resource"
	dracel "k8s.io/dynamic-resource-allocation/cel"
)

func main() {
	if len(os.Args) < 2 {
		usage()
	}
	mode := os.Args[1]

	switch mode {
	case "parse":
		runParse(readInputs(os.Args[2:]))
	case "match":
		// An optional leading device JSON (starts with '{') sets the device to
		// match against; without it the device is empty, which is all a
		// deviceless quantity()/semver() check needs.
		args := os.Args[2:]
		device := dracel.Device{}
		if len(args) > 0 && strings.HasPrefix(strings.TrimSpace(args[0]), "{") {
			device = parseDevice(args[0])
			args = args[1:]
		}
		runMatch(readInputs(args), device)
	default:
		usage()
	}
}

func usage() {
	fmt.Fprintln(os.Stderr, "usage:")
	fmt.Fprintln(os.Stderr, "  oracle parse [quantity...]            -> ok / canonical form")
	fmt.Fprintln(os.Stderr, "  oracle match [device-json] [expr...]  -> bool / error")
	fmt.Fprintln(os.Stderr, "")
	fmt.Fprintln(os.Stderr, "quantity/expr inputs come from args, or one per line on stdin if none given.")
	fmt.Fprintln(os.Stderr, "match takes an OPTIONAL leading device JSON; without one the device is empty")
	fmt.Fprintln(os.Stderr, "(enough for deviceless quantity()/semver() checks). device-json shape:")
	fmt.Fprintln(os.Stderr, "  {\"driver\":\"d\",\"attributes\":{\"name\":{\"string|bool|int|version\":v}},")
	fmt.Fprintln(os.Stderr, "   \"capacity\":{\"name\":{\"value\":\"<quantity>\"}}}")
	os.Exit(2)
}

// readInputs returns args verbatim, or each non-empty line of stdin when no
// args are given.
func readInputs(args []string) []string {
	if len(args) > 0 {
		return args
	}
	var in []string
	sc := bufio.NewScanner(os.Stdin)
	sc.Buffer(make([]byte, 1<<20), 1<<20)
	for sc.Scan() {
		line := sc.Text()
		if strings.TrimSpace(line) == "" {
			continue
		}
		in = append(in, line)
	}
	return in
}

// runParse reports, for each input, whether resource.ParseQuantity accepts it
// and the parsed Quantity's canonical String(). This is the oracle for
// quantity.py's parse()/isQuantity().
func runParse(inputs []string) {
	var b strings.Builder
	for _, in := range inputs {
		q, err := resource.ParseQuantity(in)
		if err != nil {
			fmt.Fprintf(&b, "%-28q reject\n", in)
			continue
		}
		fmt.Fprintf(&b, "%-28q ok  %s\n", in, q.String())
	}
	emit(b.String())
}

// runMatch compiles and evaluates each CEL expression through the DRA device
// selector compiler (k8s.io/dynamic-resource-allocation/cel) - the exact env a
// real DRA selector compiles against, and the env cel.py/quantity.py/semver.py
// reimplement. Using it (rather than a hand-built cel-go env) gets four things
// right at once:
//
//   - the quantity() and semver() libraries, including semver's normalize
//     overload (which the bare apiserver SemverLib() leaves off by default);
//   - upstream's STRICT call surface, so e.g. quantity(...).sign() is a compile
//     error (sign is a global function) where celpy accepts it;
//   - the real `device` OBJECT type, so has(device.attributes["domain"]) is a
//     compile error - cel-go's has() macro rejects an index argument, and only
//     upstream's declared type reproduces that;
//   - real attribute/capacity matching, when a device is supplied.
//
// Each expression is evaluated against the given device. An empty Device{}
// still answers deviceless quantity()/semver() checks and domain-presence ("x"
// in device.attributes); an expression that reads a concrete attribute/capacity
// value needs a device that carries it (else eval-error - the value is unbound).
func runMatch(inputs []string, device dracel.Device) {
	// GetCompiler returns a cached singleton, so calling it per expression is
	// cheap; its concrete type is unexported, so we use it inline rather than
	// passing it around. At the pinned k8s version it takes no feature gates and
	// compiles against the default-off DRA surface, which is the subset cel.py
	// reimplements.
	c := dracel.GetCompiler()
	var b strings.Builder
	for _, expr := range inputs {
		// DisableCostEstimation: we want parity of the result, not the
		// worst-case cost estimate.
		result := c.CompileCELExpression(expr, dracel.Options{DisableCostEstimation: true})
		b.WriteString(fmt.Sprintf("%-60s %s\n", expr, evalResult(result, device)))
	}
	emit(b.String())
}

func evalResult(result dracel.CompilationResult, device dracel.Device) string {
	if result.Error != nil {
		return "compile-error"
	}
	matches, _, err := result.DeviceMatches(context.Background(), device)
	if err != nil {
		return "eval-error"
	}
	if matches {
		return "true"
	}
	return "false"
}

// deviceJSON is the wire shape of a `match`-mode device. It mirrors the dict
// cel.py's matches() consumes (and the test _device(...) fixtures produce): an
// attribute is exactly one of string/bool/int/version; a capacity is a quantity
// string under "value". A qualified attribute/capacity name ("domain/id") lands
// under its own domain; a bare name defaults to the driver's domain (upstream's
// parseQualifiedName, which DeviceMatches applies).
type deviceJSON struct {
	Driver     string                       `json:"driver"`
	Attributes map[string]attributeJSON     `json:"attributes"`
	Capacity   map[string]map[string]string `json:"capacity"`
}

type attributeJSON struct {
	String  *string `json:"string"`
	Bool    *bool   `json:"bool"`
	Int     *int64  `json:"int"`
	Version *string `json:"version"`
}

// parseDevice builds a DRA Device from the match-mode JSON. It exits on bad
// input rather than returning an error - it's a dev tool, and a malformed device
// is a usage mistake to surface immediately.
func parseDevice(s string) dracel.Device {
	var dj deviceJSON
	if err := json.Unmarshal([]byte(s), &dj); err != nil {
		fmt.Fprintln(os.Stderr, "parse device JSON:", err)
		os.Exit(2)
	}

	dev := dracel.Device{
		Driver:     dj.Driver,
		Attributes: make(map[resourceapi.QualifiedName]resourceapi.DeviceAttribute, len(dj.Attributes)),
		Capacity:   make(map[resourceapi.QualifiedName]resourceapi.DeviceCapacity, len(dj.Capacity)),
	}
	for name, a := range dj.Attributes {
		dev.Attributes[resourceapi.QualifiedName(name)] = resourceapi.DeviceAttribute{
			StringValue:  a.String,
			BoolValue:    a.Bool,
			IntValue:     a.Int,
			VersionValue: a.Version,
		}
	}
	for name, c := range dj.Capacity {
		dev.Capacity[resourceapi.QualifiedName(name)] = resourceapi.DeviceCapacity{
			Value: resource.MustParse(c["value"]),
		}
	}
	return dev
}

// emit writes the assembled output to stdout, failing loudly if the write does.
func emit(s string) {
	if _, err := io.WriteString(os.Stdout, s); err != nil {
		fmt.Fprintln(os.Stderr, "write:", err)
		os.Exit(1)
	}
}
