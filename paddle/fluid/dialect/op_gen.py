# Copyright (c) 2023 PaddlePaddle Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import os

import yaml

# =====================================
# String Template for h file code gen
# =====================================
NAMESPACE_GARD_TEMPLATE = """namespace {namespace} {{
{input}
}} // namespace {namespace}"""

H_FILE_TEMPLATE = """#ifdef GET_OP_LIST
#undef GET_OP_LIST
{op_declare}
#else

#include "paddle/ir/core/op_base.h"

{input}
#endif
"""

GET_OP_LIST_TEMPALTE = """{}
"""

OP_DECLARE_TEMPLATE = """
class {op_name} : public ir::Op<{op_name}{interfaces}{traits}> {{
 public:
  using Op::Op;
  static const char *name() {{ return "{dialect_op_name}"; }}
  {attribute_declare}
  static constexpr uint32_t attributes_num = {attribute_num};
  static void verify(const std::vector<ir::OpResult> &inputs, const std::vector<ir::Type> &outputs, const ir::AttributeMap &attributes);
{get_inputs_and_outputs}
}};
"""
op_0_attribute_declare_str = (
    "static constexpr const char **attributes_name = nullptr;"
)
op_n_attribute_declare_str = (
    "static const char *attributes_name[{attribute_num}];"
)

OP_GET_INPUT_TEMPLATE = """  ir::OpOperand {input_name}() {{ return operation()->GetOperandByIndex({input_index}); }}
"""
OP_GET_OUTPUT_TEMPLATE = """  ir::OpResult {output_name}() {{ return operation()->GetResultByIndex({output_index}); }}
"""

# =====================================
# String Template for cc file code gen
# =====================================
CC_FILE_TEMPLATE = """#include "{h_file}"
#include "paddle/fluid/dialect/pd_type.h"
#include "paddle/fluid/dialect/pd_attribute.h"
#include "paddle/ir/core/builtin_attribute.h"
#include "paddle/ir/core/builtin_type.h"
#include "paddle/ir/core/ir_context.h"
#include "paddle/phi/core/enforce.h"

{input}
"""

OP_N_ATTRIBUTE_DEFINED_TEMPLATE = """
const char *{op_name}::attributes_name[{attribute_num}] = {{ {attribute_names} }};
"""

OP_VERIFY_TEMPLATE = """
void {op_name}::verify(const std::vector<ir::OpResult> &inputs, const std::vector<ir::Type> &outputs, const ir::AttributeMap &attributes) {{
  VLOG(4) << "Verifying inputs, outputs and attributes for: {op_name}.";

  // Verify inputs type:
  PADDLE_ENFORCE_EQ(inputs.size(), {inputs_size},
                    phi::errors::PreconditionNotMet("The size %d of inputs must be equal to {inputs_size}.", inputs.size()));
  {inputs_type_check}
  // Verify outputs type:
  PADDLE_ENFORCE_EQ(outputs.size(), {outputs_size},
                    phi::errors::PreconditionNotMet("The size %d of outputs must be equal to {outputs_size}.", outputs.size()));
  {outputs_type_check}
  // Verify if attributes contain attribute name in attributes_name:
  {attributes_check}
}}
"""

INPUT_TYPE_CHECK_TEMPLATE = """PADDLE_ENFORCE_EQ(inputs[{index}].type().isa<{standard}>(), true,
                    phi::errors::PreconditionNotMet("Type validation failed for the {index}th input."));
  """
INPUT_VECTORTYPE_CHECK_TEMPLATE = """if (inputs[{index}].type().isa<ir::VectorType>()) {{
    for (size_t i = 0; i < inputs[{index}].type().dyn_cast<ir::VectorType>().size(); i++) {{
      PADDLE_ENFORCE_EQ(inputs[{index}].type().dyn_cast<ir::VectorType>()[i].isa<{standard}>(), true,
                        phi::errors::PreconditionNotMet("Type validation failed for the {index}th input."));
    }}
  }} else {{
    PADDLE_ENFORCE_EQ(inputs[{index}].type().isa<{standard}>(), true,
                      phi::errors::PreconditionNotMet("Type validation failed for the {index}th input."));
  }}
  """
INPUT_OPTIONAL_TYPE_CHECK_TEMPLATE = """if (inputs[{index}]) {{
    PADDLE_ENFORCE_EQ(inputs[{index}].type().isa<{standard}>(), true,
                      phi::errors::PreconditionNotMet("Type validation failed for the {index}th input."));
  }}
  """
INPUT_OPTIONAL_VECTORTYPE_CHECK_TEMPLATE = """if (inputs[{index}]) {{
    if (inputs[{index}].type().isa<ir::VectorType>()) {{
      for (size_t i = 0; i < inputs[{index}].type().dyn_cast<ir::VectorType>().size(); i++) {{
        PADDLE_ENFORCE_EQ(inputs[{index}].type().dyn_cast<ir::VectorType>()[i].isa<{standard}>(), true,
                          phi::errors::PreconditionNotMet("Type validation failed for the {index}th input."));
      }}
    }} else {{
      PADDLE_ENFORCE_EQ(inputs[{index}].type().isa<{standard}>(), true,
                        phi::errors::PreconditionNotMet("Type validation failed for the {index}th input."));
    }}
  }}
  """

OUTPUT_TYPE_CHECK_TEMPLATE = """PADDLE_ENFORCE_EQ(outputs[{index}].isa<{standard}>(), true,
                    phi::errors::PreconditionNotMet("Type validation failed for the {index}th output."));
  """
OUTPUT_VECTORTYPE_CHECK_TEMPLATE = """if (outputs[{index}].isa<ir::VectorType>()) {{
    for (size_t i = 0; i < outputs[{index}].dyn_cast<ir::VectorType>().size(); i++) {{
      PADDLE_ENFORCE_EQ(outputs[{index}].dyn_cast<ir::VectorType>()[i].isa<{standard}>(), true,
                        phi::errors::PreconditionNotMet("Type validation failed for the {index}th output."));
    }}
  }} else {{
    PADDLE_ENFORCE_EQ(outputs[{index}].isa<{standard}>(), true,
                      phi::errors::PreconditionNotMet("Type validation failed for the {index}th output."));
  }}
  """
OUTPUT_OPTIONAL_TYPE_CHECK_TEMPLATE = """if (outputs[{index}]) {{
    PADDLE_ENFORCE_EQ(outputs[{index}].isa<{standard}>(), true,
                      phi::errors::PreconditionNotMet("Type validation failed for the {index}th output."));
  }}
  """
OUTPUT_OPTIONAL_VECTORTYPE_CHECK_TEMPLATE = """if (outputs[{index}]) {{
    if (outputs[{index}].isa<ir::VectorType>()) {{
      for (size_t i = 0; i < outputs[{index}].dyn_cast<ir::VectorType>().size(); i++) {{
        PADDLE_ENFORCE_EQ(outputs[{index}].dyn_cast<ir::VectorType>()[i].isa<{standard}>(), true,
                          phi::errors::PreconditionNotMet("Type validation failed for the {index}th output."));
      }}
    }} else {{
      PADDLE_ENFORCE_EQ(outputs[{index}].isa<{standard}>(), true,
                        phi::errors::PreconditionNotMet("Type validation failed for the {index}th output."));
    }}
  }}
  """

ATTRIBUTE_CHECK_TEMPLATE = """PADDLE_ENFORCE_EQ(attributes.at("{attribute_name}").isa<{standard}>(), true,
                    phi::errors::PreconditionNotMet("Type of attribute: {attribute_name} is not right."));
  """
ATTRIBUTE_VECTOR_CHECK_TEMPLATE = """PADDLE_ENFORCE_EQ(attributes.at("{attribute_name}").isa<ir::ArrayAttribute>(), true,
                    phi::errors::PreconditionNotMet("Type of attribute: {attribute_name} is not right."));
  for (size_t i = 0; i < attributes.at("{attribute_name}").dyn_cast<ir::ArrayAttribute>().size(); i++) {{
    PADDLE_ENFORCE_EQ(attributes.at("{attribute_name}").dyn_cast<ir::ArrayAttribute>()[i].isa<{standard}>(), true,
                      phi::errors::PreconditionNotMet("Type of attribute: {attribute_name} is not right."));
  }}
  """


# =====================================
# Parse Op information from Yaml item
# =====================================
class OpInfoParser:
    def __init__(self, op_yaml_item):
        self.op_yaml_item = op_yaml_item
        self.op_phi_name = self.parse_op_phi_name()

        self.input_name_list = self.parse_input_name_list()
        self.input_type_list = self.parse_input_type_list()
        self.input_optional_list = self.parse_input_optional_list()
        self.cross_check(
            self.input_name_list, self.input_type_list, self.input_optional_list
        )

        self.output_name_list = self.parse_output_name_list()
        self.output_type_list = self.parse_output_type_list()
        self.output_optional_list = self.parse_output_optional_list()
        self.cross_check(
            self.output_name_list,
            self.output_type_list,
            self.output_optional_list,
        )

        self.attribute_name_list = self.parse_attribute_name_list()
        self.attribute_type_list = self.parse_attribute_type_list()
        self.cross_check(self.attribute_name_list, self.attribute_type_list)

    def cross_check(self, name_list, type_list, optional_list=None):
        assert len(name_list) == len(
            type_list
        ), "name list size != type list size."
        if optional_list is not None:
            assert len(type_list) == len(
                optional_list
            ), "type list size != optional list size."

    def parse_input_name_list(self):
        name_list = []
        for input_info in self.op_yaml_item['inputs']:
            name_list.append(input_info['name'])
        return name_list

    def parse_input_type_list(self):
        input_types_map = {
            'Tensor': 'paddle::dialect::DenseTensorType',
            'Tensor[]': 'ir::VectorType<paddle::dialect::DenseTensorType>',
        }
        type_list = []
        for input_info in self.op_yaml_item['inputs']:
            assert (
                input_info['typename'] in input_types_map
            ), f"{self.op_phi_name} : Input type error: the input type only support Tensor and Tensor[], but now is {input_info['typename']}."
            type_list.append(input_types_map[input_info['typename']])
        return type_list

    def parse_input_optional_list(self):
        optional_list = []
        for input_info in self.op_yaml_item['inputs']:
            optional_list.append(input_info['optional'])
        return optional_list

    def parse_output_name_list(self):
        name_list = []
        for output_info in self.op_yaml_item['outputs']:
            name_list.append(output_info['name'])
        return name_list

    def parse_output_type_list(self):
        output_type_map = {
            'Tensor': 'paddle::dialect::DenseTensorType',
            'Tensor[]': 'ir::VectorType<paddle::dialect::DenseTensorType>',
        }
        type_list = []
        for output_info in self.op_yaml_item['outputs']:
            assert (
                output_info['typename'] in output_type_map
            ), f"{self.op_phi_name} : Output type error: the output type only support Tensor and Tensor[], but now is {output_info['typename']}."
            type_list.append(output_type_map[output_info['typename']])
        return type_list

    def parse_output_optional_list(self):
        optional_list = []
        for output_info in self.op_yaml_item['outputs']:
            if 'optional' in output_info:
                optional_list.append(output_info['optional'])
            else:
                optional_list.append(False)
        return optional_list

    def parse_attribute_name_list(self):
        name_list = []
        for attribute_info in self.op_yaml_item['attrs']:
            name_list.append(attribute_info['name'])
        return name_list

    def parse_attribute_type_list(self):
        attr_types_map = {
            'IntArray': 'paddle::dialect::IntArrayAttribute',
            'Scalar': 'paddle::dialect::ScalarAttribute',
            'Scalar(int)': 'paddle::dialect::ScalarAttribute',
            'Scalar(int64_t)': 'paddle::dialect::ScalarAttribute',
            'Scalar(float)': 'paddle::dialect::ScalarAttribute',
            'Scalar(dobule)': 'paddle::dialect::ScalarAttribute',
            'Scalar[]': 'ir::ArrayAttribute<paddle::dialect::ScalarAttribute>',
            'int': 'ir::Int32_tAttribute',
            'int32_t': 'ir::Int32_tAttribute',
            'int64_t': 'ir::Int64_tAttribute',
            'long': 'ir::LongAttribute',
            'size_t': 'ir::Size_tAttribute',
            'float': 'ir::FloatAttribute',
            'float[]': 'ir::ArrayAttribute<ir::FloatAttribute>',
            'double': 'ir::DoubleAttribute',
            'bool': 'ir::BoolAttribute',
            'bool[]': 'ir::ArrayAttribute<ir::BoolAttribute>',
            'str': 'ir::StrAttribute',
            'str[]': 'ir::ArrayAttribute<ir::StrAttribute>',
            'Place': 'paddle::dialect::PlaceAttribute',
            'DataLayout': 'paddle::dialect::DataLayoutAttribute',
            'DataType': 'paddle::dialect::DataTypeAttribute',
            'int64_t[]': 'ir::ArrayAttribute<ir::Int64_tAttribute>',
            'int[]': 'ir::ArrayAttribute<ir::Int32_tAttribute>',
        }
        type_list = []
        for attribute_info in self.op_yaml_item['attrs']:
            assert (
                attribute_info['typename'] in attr_types_map
            ), f"{self.op_phi_name} : Attr type error."
            type_list.append(attr_types_map[attribute_info['typename']])
        return type_list

    def parse_op_phi_name(self):
        return self.op_yaml_item['name']


def to_pascal_case(s):
    words = s.split("_")
    if s[-1] == "_":
        return "".join([word.capitalize() for word in words]) + "_"
    else:
        return "".join([word.capitalize() for word in words]) + ""


# =====================================
# Generate op definition files
# =====================================
def OpGenerator(
    op_yaml_files,
    namespaces,
    dialect_name,
    op_def_h_file,
    op_def_cc_file,
):
    # (1) Prepare: Delete existing old files: pd_op.h.tmp, pd_op.cc.tmp
    if os.path.exists(op_def_h_file):
        os.remove(op_def_h_file)
    if os.path.exists(op_def_cc_file):
        os.remove(op_def_cc_file)

    # (2) Prepare: Get all op item in all op_yaml_files
    op_yaml_items = []
    for yaml_file in op_yaml_files:
        with open(yaml_file, "r") as f:
            ops = yaml.safe_load(f)
            op_yaml_items = op_yaml_items + ops
    op_info_items = []
    for op in op_yaml_items:
        op_info_items.append(OpInfoParser(op))

    # (3) CodeGen: Traverse op_info_items and generate
    ops_name_list = []  # all op class name store in this list
    ops_declare_list = []  # all op class declare store in this list
    ops_defined_list = []  # all op class defined store in this list
    for op_info in op_info_items:
        # get op info
        op_name = op_info.op_phi_name
        op_class_name = to_pascal_case(op_name) + "Op"
        op_dialect_name = dialect_name + "." + op_name
        op_input_name_list = op_info.input_name_list
        op_input_type_list = op_info.input_type_list
        op_input_optional_list = op_info.input_optional_list
        op_output_name_list = op_info.output_name_list
        op_output_type_list = op_info.output_type_list
        op_output_optional_list = op_info.output_optional_list
        op_attribute_name_list = op_info.attribute_name_list
        op_attribute_type_list = op_info.attribute_type_list
        op_interfaces = []
        op_traits = []

        # gen interface/trait str
        op_interfaces_str = ""
        if len(op_interfaces) > 0:
            op_interfaces_str = "," + ",".join(op_interfaces)
        op_traits_str = ""
        if len(op_interfaces) > 0:
            op_traits_str = "," + ",".join(op_traits)

        op_get_inputs_outputs_str = ""
        for idx in range(len(op_input_name_list)):
            op_get_inputs_outputs_str += OP_GET_INPUT_TEMPLATE.format(
                input_name=op_input_name_list[idx], input_index=idx
            )
        for idx in range(len(op_output_name_list)):
            op_get_inputs_outputs_str += OP_GET_OUTPUT_TEMPLATE.format(
                output_name=op_output_name_list[idx], output_index=idx
            )

        # gen op_declare_str/op_defined_str
        if len(op_attribute_name_list) == 0:
            op_declare_str = OP_DECLARE_TEMPLATE.format(
                op_name=op_class_name,
                dialect_op_name=op_dialect_name,
                interfaces=op_interfaces_str,
                traits=op_traits_str,
                attribute_declare=op_0_attribute_declare_str,
                attribute_num=0,
                get_inputs_and_outputs=op_get_inputs_outputs_str,
            )
            op_defined_str = ""
        else:
            op_declare_str = OP_DECLARE_TEMPLATE.format(
                op_name=op_class_name,
                dialect_op_name=op_dialect_name,
                interfaces=op_interfaces_str,
                traits=op_traits_str,
                attribute_declare=op_n_attribute_declare_str.format(
                    attribute_num=len(op_attribute_name_list)
                ),
                attribute_num=len(op_attribute_name_list),
                get_inputs_and_outputs=op_get_inputs_outputs_str,
            )
            attribute_names_str = (
                '"' + '", "'.join(op_attribute_name_list) + '"'
            )
            op_defined_str = OP_N_ATTRIBUTE_DEFINED_TEMPLATE.format(
                op_name=op_class_name,
                attribute_num=len(op_attribute_name_list),
                attribute_names=attribute_names_str,
            )

        # generate op verify function: inputs_type_check_str
        if len(op_input_type_list) == 0:
            inputs_type_check_str = (
                "// Inputs num is 0, not need to check inputs type."
            )
        else:
            inputs_type_check_str = ""
        for idx in range(len(op_input_type_list)):
            input_type = op_input_type_list[idx]
            is_optional = op_input_optional_list[idx]
            is_vector = False
            if input_type.startswith("ir::VectorType<"):
                is_vector = True
                input_type = input_type[15:-1]
            check_str = ""
            if is_optional:
                if is_vector:
                    check_str = INPUT_OPTIONAL_VECTORTYPE_CHECK_TEMPLATE.format(
                        index=idx, standard=input_type
                    )
                else:
                    check_str = INPUT_OPTIONAL_TYPE_CHECK_TEMPLATE.format(
                        index=idx, standard=input_type
                    )
            else:
                if is_vector:
                    check_str = INPUT_VECTORTYPE_CHECK_TEMPLATE.format(
                        index=idx, standard=input_type
                    )
                else:
                    check_str = INPUT_TYPE_CHECK_TEMPLATE.format(
                        index=idx, standard=input_type
                    )
            inputs_type_check_str += check_str

        # generate op verify function: outputs_type_check_str
        if len(op_output_type_list) == 0:
            outputs_type_check_str = (
                "// Outputs num is 0, not need to check outputs type."
            )
        else:
            outputs_type_check_str = ""
        for idx in range(len(op_output_type_list)):
            output_type = op_output_type_list[idx]
            is_optional = op_output_optional_list[idx]
            is_vector = False
            if output_type.startswith("ir::VectorType<"):
                is_vector = True
                output_type = output_type[15:-1]
            check_str = ""
            if is_optional:
                if is_vector:
                    check_str = (
                        OUTPUT_OPTIONAL_VECTORTYPE_CHECK_TEMPLATE.format(
                            index=idx, standard=output_type
                        )
                    )
                else:
                    check_str = OUTPUT_OPTIONAL_TYPE_CHECK_TEMPLATE.format(
                        index=idx, standard=output_type
                    )
            else:
                if is_vector:
                    check_str = OUTPUT_VECTORTYPE_CHECK_TEMPLATE.format(
                        index=idx, standard=output_type
                    )
                else:
                    check_str = OUTPUT_TYPE_CHECK_TEMPLATE.format(
                        index=idx, standard=output_type
                    )
            outputs_type_check_str += check_str

        # generate op verify function: attributes_check_str
        if len(op_attribute_name_list) == 0:
            attributes_check_str = (
                "// Attributes num is 0, not need to check attributes type."
            )
        else:
            attributes_check_str = ""
        for idx in range(len(op_attribute_name_list)):
            attribute_name = op_attribute_name_list[idx]
            attribute_type = op_attribute_type_list[idx]
            if attribute_type.startswith("ir::ArrayAttribute<"):
                attribute_type = attribute_type[19:-1]
                attributes_check_str += ATTRIBUTE_VECTOR_CHECK_TEMPLATE.format(
                    attribute_name=attribute_name, standard=attribute_type
                )
            else:
                attributes_check_str += ATTRIBUTE_CHECK_TEMPLATE.format(
                    attribute_name=attribute_name, standard=attribute_type
                )

        # generate op verify function
        op_verify_str = OP_VERIFY_TEMPLATE.format(
            op_name=op_class_name,
            inputs_size=len(op_input_type_list),
            outputs_size=len(op_output_type_list),
            inputs_type_check=inputs_type_check_str,
            outputs_type_check=outputs_type_check_str,
            attributes_check=attributes_check_str,
        )

        ops_name_list.append(op_class_name)
        ops_declare_list.append(op_declare_str)
        ops_defined_list.append(op_defined_str)
        ops_defined_list.append(op_verify_str)

    # (4) Generate head file str
    op_namespaces_prev = ""
    for name in namespaces:
        op_namespaces_prev += name + "::"
    ops_name_with_namespace_list = []
    for name in ops_name_list:
        ops_name_with_namespace_list.append(op_namespaces_prev + name)
    op_list_str = GET_OP_LIST_TEMPALTE.format(
        ", ".join(ops_name_with_namespace_list)
    )  # Add GET_OP_LIST
    head_file_str = ""
    head_file_str += "".join(ops_declare_list)  # Add op class
    for name in reversed(namespaces):
        head_file_str = NAMESPACE_GARD_TEMPLATE.format(
            namespace=name, input=head_file_str
        )  # Add namespaces
    head_file_str = H_FILE_TEMPLATE.format(
        op_declare=op_list_str, input=head_file_str
    )  # Add head

    # (5) Generate source file str
    source_file_str = "".join(ops_defined_list)  # Add op define
    for name in reversed(namespaces):
        source_file_str = NAMESPACE_GARD_TEMPLATE.format(
            namespace=name, input=source_file_str
        )  # Add namespaces
    source_file_str = CC_FILE_TEMPLATE.format(
        h_file=op_def_h_file, input=source_file_str
    )  # Add head

    # (5) Generate pd_op.h.tmp, pd_op.cc.tmp
    with open(op_def_h_file, 'a') as f:
        f.write(head_file_str)
    with open(op_def_cc_file, 'a') as f:
        f.write(source_file_str)


# =====================================
# Script parameter parsing
# =====================================
def ParseArguments():
    parser = argparse.ArgumentParser(
        description='Generate Dialect OP Definition Files By Yaml'
    )
    parser.add_argument('--op_yaml_files', type=str)
    parser.add_argument('--op_compat_yaml_file', type=str)
    parser.add_argument('--namespaces', type=str)
    parser.add_argument('--dialect_name', type=str)
    parser.add_argument('--op_def_h_file', type=str)
    parser.add_argument('--op_def_cc_file', type=str)
    return parser.parse_args()


# =====================================
# Main
# =====================================
if __name__ == "__main__":
    # parse arguments
    args = ParseArguments()
    op_yaml_files = args.op_yaml_files.split(",")
    op_compat_yaml_file = args.op_compat_yaml_file
    namespaces = []
    if args.namespaces is not None:
        namespaces = args.namespaces.split(",")
    dialect_name = args.dialect_name
    op_def_h_file = args.op_def_h_file
    op_def_cc_file = args.op_def_cc_file

    # auto code generate
    OpGenerator(
        op_yaml_files,
        namespaces,
        dialect_name,
        op_def_h_file,
        op_def_cc_file,
    )