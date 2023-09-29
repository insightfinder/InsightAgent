package tools

import (
	"github.com/bigkevmcd/go-configparser"
	"strings"
)

type PostProcessor struct {
	target                  string
	hideComponentNamePrefix string
	nodeComponentName       string
}

func (processor *PostProcessor) Initialize(configFile *configparser.ConfigParser) {

	// Initialize target
	processor.target, _ = configFile.Get("general", "target")

	// Initialize nodeComponentName
	processor.nodeComponentName, _ = configFile.Get("general", "node_component_name")

	// Initialize hideComponentNameRegx
	processor.hideComponentNamePrefix, _ = configFile.Get("general", "hide_component_name_prefix")

}

func (processor *PostProcessor) ProcessComponentName(componentName string) string {
	if processor.target == "node" {
		return processor.nodeComponentName
	} else {
		if processor.hideComponentNamePrefix != "" {
			return strings.TrimPrefix(componentName, processor.hideComponentNamePrefix)
		}
	}
	return componentName
}
