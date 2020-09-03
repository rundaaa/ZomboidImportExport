# Author: Jab (or 40BlocksUnder) | Joshua Edwards
# Link for more info: http://theindiestone.com/forums/index.php/topic/12864-blender
# Exports models to Zomboid format.

bl_info = {
    "name": "ZomboidExport",
    "description": "Exports models to Zomboid format.",
    "author": "Jab",
    "version": (1, 0),
    "blender": (2, 79, 0),
    "location": "",
    "warning": "", # used for warning icon and text in addons panel
    "wiki_url": "http://theindiestone.com/forums/index.php/topic/12864-blender"
                "Scripts/My_Script",
    "tracker_url": "https://developer.blender.org/maniphest/task/edit/form/2/",
    "support": "COMMUNITY",
    "category": "Import-Export",
}


import io, math, bmesh, bpy
from bpy_extras.io_utils import ExportHelper
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy.types import Operator
from mathutils import Vector, Euler, Quaternion, Matrix


class ZomboidExport(Operator, ExportHelper):
    bl_idname    = "zomboid.export_model"
    bl_label     = "Export a Zomboid Model"
    filename_ext = ".txt"
    filter_glob  = StringProperty(
            default="*.txt",
            options={'HIDDEN'},
            )

    #use_setting = BoolProperty(
    #        name="Example Boolean",
    #        description="Example Tooltip",
    #        default=True,
    #        )

    #type = EnumProperty(
    #        name="Example Enum",
    #        description="Choose between two items",
    #        items=(('OPT_A', "First Option", "Description one"),
    #               ('OPT_B', "Second Option", "Description two")),
    #        default='OPT_A',
    #        )
    
    
    def prepare_mesh(self):
        
        self.object_original = bpy.context.active_object
        # Grab the name of the selected object
        self.mesh_name = self.object_original.name
        
        # Duplicate the object to modify without affecting the actual model
        bpy.ops.object.duplicate()
        
        object = self.object = bpy.context.active_object
        mesh   = self.mesh   = object.data

        # We need to be in edit-mode to fix up the duplicate
        bpy.ops.object.mode_set(mode = 'EDIT')
        
        bpy.ops.mesh.select_all(action='SELECT')
        
        # In order to be a valid format, the mesh needs to be
        #    in triangulated.
        bpy.ops.mesh.quads_convert_to_tris()
        
        # Go back to Object mode to apply polygon modifications.
        bpy.ops.object.mode_set(mode = 'OBJECT')
        bpy.ops.object.mode_set(mode = 'EDIT')
        bpy.ops.object.mode_set(mode = 'OBJECT')
        # Grab the count of vertices.
        self.mesh_vertex_count = len(object.data.vertices)
        
        # Create a boolean for asking if the mesh has uv map data 
        has_uv_mapping = self.mesh_has_uv_mapping = len(mesh.uv_textures) > 0
        
        # Assign UV Map data if it exists.
        if has_uv_mapping:
            self.vertex_stride_element_count += 1
            self.uv_texture = mesh.uv_textures.active.data[:]
            self.uv_layer   = mesh.uv_layers.active.data[:]
            
        # Calculate face normals
        mesh.calc_normals_split()
        
        self.mesh_loops = mesh.loops
        
        for modifier in object.modifiers:
            if modifier.type == 'ARMATURE':
                if object.parent.type == 'ARMATURE':
                    if object.parent['ZOMBOID_ARMATURE'] == 1:
                        self.vertex_stride_element_count += 3
                        self.armature = object.parent.data
                        self.mesh_has_bone_weights  = True
                        self.mesh_has_tangent_array = True
                        print("Armature modifier detected. Exporting with bone weights.")
            
        
        
        
    def process_mesh(self):
        
        self.global_matrix = Matrix()
        self.mesh_matrix   = self.object.matrix_world

        object      = self.object
        mesh        = self.mesh
        mesh_matrix = self.mesh_matrix

        if self.mesh_has_bone_weights:
            vert_weight_id    = []
            vert_weight_value = []
            
            bone_id_table     = get_bone_id_table(object.parent)
            weight_data       = mesh_to_weight_list(object, mesh)
            weight_bone_names = weight_data[0]
            weight_vert_data  = weight_data[1]
            
            for vid, vert in enumerate(mesh.vertices):
                weights = ""
                indexes = ""
                offset = 0
     
                for bid, bone_value in enumerate(weight_vert_data[vid]):
                    if bone_value > 0.0:
                       bone_id  = bone_id_table[weight_bone_names[bid]]
                       weights += str(round(bone_value, 8)) + ", "
                       indexes += str(bone_id) + ", "
                       offset  += 1
                
                if offset < 4:
                    while offset < 4:
                        weights += "-1.0, "
                        indexes += "0, "
                        offset  += 1
                        
                vert_weight_id.append(indexes[:-2])
                vert_weight_value.append(weights[:-2])
                
                
        mesh.update(calc_tessface=True)
        
        for f in mesh.polygons:
            face = Face()
            face.id = f.index
            for i in f.loop_indices:
                l = mesh.loops[i]
                v = mesh.vertices[l.vertex_index]
                vert = Vertex()
                vid = vert.id = l.vertex_index
                vert.co = v.co
                vert.normal = v.normal
                
                # If UV mapping, then add this data.
                if self.mesh_has_uv_mapping:
                    uvl = 0
                    for j,ul in enumerate(mesh.uv_layers):
                        vert.texture_coord = ul.data[l.index].uv
                        uvl += 1
                
                # If Bone Weights, add this data.
                if self.mesh_has_bone_weights:
                    vert.blend_weight = vert_weight_value[vid]
                    vert.blend_index  = vert_weight_id[vid]
                
                face.verts.append(vert)
                
            self.faces.append(face)
        
        # Optimize the face vert count
        
        # Temporary containers & flags
        verts      = []
        has_vert   = dict()
        vert_index = dict()
        
        # Offset for the new index
        vert_offset = 0
        
        # Go through each face
        for f in self.faces:
            # Go through each vertex
            for index in range(0,len(face.verts)):
                # Grab the vertex
                f_v = f.verts[index]
                
                # Create the Unique key for compared data.
                key = str(f_v.co) + " " + str(f_v.texture_coord)
                try:
                    # Ask if vert key exists.
                    has_v = has_vert[key]
                    # If so,
                    if has_v:
                        # Point the face's vert index there instead.
                        f.vert_ids.append(vert_index[key])
                    # Add a false clause just in-case.
                    else:
                        # Set the key flag to True.
                        has_vert[key]   = True
                        # Set the vert's ID to the new one.
                        f_v.id          = vert_offset
                        # Set the index container.
                        vert_index[key] = vert_offset
                        # Append the vertex's new ID to the face.
                        f.vert_ids.append(vert_offset)
                        # Add the vertex to the new array.
                        verts.append(f_v)
                        #Increment the offset for the next new Vertex.
                        vert_offset    += 1
                # This happens when not valid. Create new vertex.        
                except:
                    # Set the key flag to True.
                    has_vert[key]   = True
                    # Set the vert's ID to the new one.
                    f_v.id          = vert_offset
                    # Set the index container.
                    vert_index[key] = vert_offset
                    # Append the vertex's new ID to the face.
                    f.vert_ids.append(vert_offset)
                    # Add the vertex to the new array.
                    verts.append(f_v)
                    #Increment the offset for the next new Vertex.
                    vert_offset    += 1
            
            # Delete unused data.
            del f.verts
        
        # Delete unused data.
        del has_vert
        del vert_index
        
        self.verts = verts
        
                    
    def write_header(self, file):
        write_comment(file, "Project Zomboid Skinned Mesh")
        
        write_comment(file, "File Version:")
        write_line(file, 1.0)
        
        write_comment(file, "Model Name:")
        write_line(file, self.mesh_name)
        
        
    def write_vertex_buffer(self, file):
        
        write_comment(file, "Vertex Stride Element Count:")
        write_line(file, self.vertex_stride_element_count)
        
        # This seems to be 76 in all files.
        write_comment(file, "Vertex Stride Size (in bytes):")
        write_line(file, 76)
        
        write_comment(file, "Vertex Stride Data:")
        write_comment(file, "(Int)    Offset"    )
        write_comment(file, "(String) Type"      )
        
        offset = 0
        if self.mesh_has_vertex_array:
            write_line(file, offset                          )
            write_line(file, self.vertex_array_name          )
            offset += self.offset_vertex_array
        if self.mesh_has_normal_array:
            write_line(file, offset                          )
            write_line(file, self.normal_array_name          )
            offset += self.offset_normal_array
        if self.mesh_has_tangent_array:
            write_line(file, offset                          )
            write_line(file, self.tangent_array_name         )
            offset += self.offset_tangent_array
        if self.mesh_has_uv_mapping:
            write_line(file, offset                          )
            write_line(file, self.texture_coord_array_name   )
            offset += self.offset_texture_coord_array
        if self.mesh_has_bone_weights:
            write_line(file, offset  )
            write_line(file, self.blend_weight_array_name    )
            offset += self.offset_blend_weight_array
            write_line(file, offset )
            write_line(file, self.blend_index_array_name     )
            offset += self.offset_blend_index_array
        
        del offset
        
        write_comment(file, "Vertex Count:")
        write_line(file, len(self.verts))
        
        write_comment(file, "Vertex Buffer:")
        for vert in self.verts:
            #vert = self.verts[key]
            if self.mesh_has_vertex_array:
                write_vector_3(file, (Vector((vert.co[0], vert.co[1], vert.co[2]))))
            if self.mesh_has_normal_array:
                write_vector_3(file, (vert.normal ) )
            if self.mesh_has_tangent_array:
                write_vector_3(file, (vert.tangent) )
            if self.mesh_has_uv_mapping:
                write_uv(file, vert.texture_coord)
            if self.mesh_has_bone_weights:
                write_weights(file, vert)    
        
    def write_faces(self, file):
        
        write_comment(file, "Number of Faces:")
        write_line(file, len(self.faces))
        
        write_comment(file, "Face Data:")
        for face in self.faces:
            write_face(file, face)
    
    def execute(self, context):
        
        try:
            bpy.ops.object.mode_set(mode = 'OBJECT')
        except:
            ok = None
        
        object = self.object = bpy.context.active_object
        
        # Checks to see if selection is avaliable AND a Mesh.
        if object == None:
            print("No Mesh selected.")
            return {'FINISHED'}
        if object.type != 'MESH':
            print("Object selected is not a mesh: " + str(object.type))
            return {'FINISHED'}
        
        
        self.prepare_mesh()
        
        self.process_mesh()
        
        with io.open(self.filepath, 'w') as file:
            self.write_header(file)
            self.write_vertex_buffer(file)
            self.write_faces(file)
        
        bpy.ops.object.mode_set(mode = 'OBJECT')
        
        # If the object active is not the original, delete it.
        if bpy.context.active_object.name != self.mesh_name:
            bpy.ops.object.delete()
        
        # Reset the object selection.
        bpy.ops.object.select_pattern(pattern=self.mesh_name)
        context.scene.objects.active = self.object_original
        self.object_original = True
        
        return {'FINISHED'}

    def __init__(self):
        self.verts                              = []
        self.faces                              = []
        
        self.global_matrix                      = None
        
        self.object_original                    = None
        self.object                             = None
        self.armature                           = None
        self.mesh                               = None
        self.mesh_name                          = "Untitled_Mesh"
        self.mesh_matrix                        = None
        self.mesh_loops                         = None
        
        self.vertex_array_name                  = 'VertexArray'
        self.normal_array_name                  = 'NormalArray'
        self.tangent_array_name                 = 'TangentArray'
        self.texture_coord_array_name           = 'TextureCoordArray'
        self.blend_weight_array_name            = 'BlendWeightArray'
        self.blend_index_array_name             = 'BlendIndexArray'
        
        self.mesh_vertex_count                  = 0
        
        self.offset_vertex_array                = 12
        self.offset_normal_array                = 12
        self.offset_tangent_array               = 12
        self.offset_texture_coord_array         = 8
        self.offset_blend_weight_array          = 16
        self.offset_blend_index_array           = 0
        
        self.vertex_stride_element_count        = 2
        self.mesh_has_vertex_array              = True
        self.mesh_has_normal_array              = True
        self.mesh_has_tangent_array             = False
        self.mesh_has_uv_mapping                = False
        self.mesh_has_bone_weights              = False


class Vertex:
    
    def __init__(self):
        self.mesh_vertex                        = None
        self.polygon                            = None
        
        self.co                                 = Vector((0.0,0.0,0.0))
        self.normal                             = Vector((0.0,0.0,0.0))
        self.tangent                            = Vector((0.0,0.0,0.0))
        self.texture_coord                      = Vector((0.0,0.0))
        
        self.blend_weight                       = []
        self.blend_index                        = []
        
        self.id                                 = -1
        self.original_vert_id                   = -1
    
    
class Face:
    
    def __init__(self):
        self.vert_ids                           = []
        self.verts                              = []
        self.id                                 = -1
        
        
        
def menu_func_export(self, context):
    self.layout.operator(ZomboidExport.bl_idname, text="Text Export Operator")

def register():
    bpy.utils.register_class(ZomboidExport)
    bpy.types.INFO_MT_file_export.append(menu_func_export)


def unregister():
    bpy.utils.unregister_class(ZomboidExport)
    bpy.types.INFO_MT_file_export.remove(menu_func_export)


if __name__ == "__main__":
    register()
    bpy.ops.zomboid.export_model('INVOKE_DEFAULT')

#####################################################################################
###                                                                               ###
###   File I/O methods                                                            ###
###                                                                               ###
#####################################################################################         


# Writes a line to the file.
def write_line(file, line, new_line=True):
    
    # Converts any arbitrary primitives into a String just in-case.
    finished_line = str(line)
    
    # If new_line is true, add a newline marker at the end.
    if new_line:
        finished_line = finished_line + "\n"
    
    # Write the line to a file.
    file.write(finished_line)
    
def write(file, line):
    write_line(file, line, new_line=False)
    
    
# Writes a comment to the file.
def write_comment(file, comment):
    
    final_comment = "# " + str(comment)
    
    write_line(file, final_comment)
    
    
def write_vector_3(file, vector):
    string = str(round(vector[0], 8)) + ", " + str(round(vector[1], 8)) + ", " + str(round(vector[2], 8))
    write_line(file, string)
    

def write_uv(file, vector):
    #print("Vec2: " + str(vector))
    string = str(round(vector[0], 8)) + ", " + str(round(1.0 - vector[1], 8))
    write_line(file, string)
    
    
def write_weights(file, vector):
    write_line(file, vector.blend_weight)
    write_line(file, vector.blend_index)   
    
    
def write_array(file, array):
    string = ""
    
    for element in array:
        string += str(element) + ", "
    
    write_line(file, string[:-2])
   
    
def write_face(file, face):
    string = ""
    for index in face.vert_ids:
        string += str(index) + ", "
    
    write_line(file, string[:-2])
    
#####################################################################################
###                                                                               ###
###   Helper Methods                                                              ###
###                                                                               ###
##################################################################################### 


def mesh_to_weight_list(ob, me):
    """
    Takes a mesh and return its group names and a list of lists,
    one list per vertex.
    aligning the each vert list with the group names,
    each list contains float value for the weight.
    link: http://blender.stackexchange.com/a/653
    def author: ideasman42
    """
    
    # clear the vert group.
    group_names = [g.name for g in ob.vertex_groups]
    group_names_tot = len(group_names)

    if not group_names_tot:
        # no verts? return a vert aligned empty list
        return [[] for i in range(len(me.vertices))], []
    else:
        weight_ls = [[0.0] * group_names_tot for i in range(len(me.vertices))]

    for i, v in enumerate(me.vertices):
        for g in v.groups:
            # possible weights are out of range
            index = g.group
            if index < group_names_tot:
                weight_ls[i][index] = g.weight

    return group_names, weight_ls


def get_bone_id_table(armature):
    
    arm = armature.data
    
    bone_names = [bone.name for bone in arm.bones]
    bone_ids   = dict()
    
    
    for bone_name in bone_names:
        try:
            bone_ids[bone_name] = int(armature[bone_name])
            print(bone_ids[bone_name])
        except:
            continue
    
    return bone_ids

matrix_3_transform_z_positive = Matrix((( 1, 0, 0 )   ,( 0, 0,-1 )   ,( 0, 1, 0 )                  ))
matrix_4_transform_z_positive = Matrix((( 1, 0, 0, 0 ),( 0, 0,-1, 0 ),( 0, 1, 0, 0 ),( 0, 0, 0, 1 )))