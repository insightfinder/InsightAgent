package tools

import (
	"github.com/bigkevmcd/go-configparser"
	"strings"
)

type PostProcessor struct {
	hideComponentNamePrefix string
}

func (processor *PostProcessor) Initialize(configFile *configparser.ConfigParser) {

	// Initialize hideComponentNameRegx
	processor.hideComponentNamePrefix, _ = configFile.Get("general", "hide_component_name_prefix")
}

func (processor *PostProcessor) ProcessComponentName(componentName string) string {
	if processor.hideComponentNamePrefix != "" {
		return strings.TrimPrefix(componentName, processor.hideComponentNamePrefix)
	}
	return componentName
}
