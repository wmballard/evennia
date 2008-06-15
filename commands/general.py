"""
Generic command module. Pretty much every command should go here for
now.
"""
import time

from django.conf import settings

from apps.config.models import ConfigValue
from apps.helpsys.models import HelpEntry
import functions_general
import functions_db
import defines_global
import session_mgr
import ansi

def cmd_password(cdat):
    """
    Changes your own password.
    
    @newpass <Oldpass>=<Newpass>
    """
    session = cdat['session']
    pobject = session.get_pobject()
    args = cdat['uinput']['splitted'][1:]
    eq_args = ' '.join(args).split('=')
    oldpass = ''.join(eq_args[0])
    newpass = ''.join(eq_args[1:])
    
    if len(oldpass) == 0:    
        session.msg("You must provide your old password.")
    elif len(newpass) == 0:
        session.msg("You must provide your new password.")
    else:
        uaccount = pobject.get_user_account()
        
        if not uaccount.check_password(oldpass):
            session.msg("The specified old password isn't correct.")
        elif len(newpass) < 3:
            session.msg("Passwords must be at least three characters long.")
            return
        else:
            uaccount.set_password(newpass)
            uaccount.save()
            session.msg("Password changed.")

def cmd_emit(cdat):        
    """
    Emits something to your location.
    """
    session = cdat['session']
    pobject = session.get_pobject()
    uinput= cdat['uinput']['splitted']
    message = ' '.join(uinput[1:])
    
    if message == '':
        session.msg("Emit what?")
    else:
        pobject.get_location().emit_to_contents(message)

def cmd_wall(cdat):
    """
    Announces a message to all connected players.
    """
    session = cdat['session']
    wallstring = ' '.join(cdat['uinput']['splitted'][1:])
    pobject = session.get_pobject()
        
    if wallstring == '':
        session.msg("Announce what?")
        return
        
    message = "%s shouts \"%s\"" % (session.get_pobject().get_name(show_dbref=False), wallstring)
    functions_general.announce_all(message)

def cmd_idle(cdat):
    """
    Returns nothing, this lets the player set an idle timer without spamming
    his screen.
    """
    pass
    
def cmd_inventory(cdat):
    """
    Shows a player's inventory.
    """
    session = cdat['session']
    pobject = session.get_pobject()
    session.msg("You are carrying:")
    
    for item in pobject.get_contents():
        session.msg(" %s" % (item.get_name(),))
        
    money = int(pobject.get_attribute_value("MONEY", default=0))
    if money == 1:
        money_name = ConfigValue.objects.get_configvalue("MONEY_NAME_SINGULAR")
    else:
        money_name = ConfigValue.objects.get_configvalue("MONEY_NAME_PLURAL")

    session.msg("You have %d %s." % (money,money_name))

def cmd_look(cdat):
    """
    Handle looking at objects.
    """
    session = cdat['session']
    pobject = session.get_pobject()
    args = cdat['uinput']['splitted'][1:]

    if len(args) == 0:    
        target_obj = pobject.get_location()
    else:
        target_obj = functions_db.standard_plr_objsearch(session, ' '.join(args))
        # Use standard_plr_objsearch to handle duplicate/nonexistant results.
        if not target_obj:
            return
    
    # SCRIPT: Get the item's appearance from the scriptlink.
    session.msg(target_obj.get_scriptlink().return_appearance({
        "target_obj": target_obj,
        "pobject": pobject
    }))
            
    # SCRIPT: Call the object's script's a_desc() method.
    target_obj.get_scriptlink().a_desc({
        "target_obj": pobject
    })
            
def cmd_get(cdat):
    """
    Get an object and put it in a player's inventory.
    """
    session = cdat['session']
    pobject = session.get_pobject()
    args = cdat['uinput']['splitted'][1:]
    plr_is_staff = pobject.is_staff()

    if len(args) == 0:    
        session.msg("Get what?")
        return
    else:
        target_obj = functions_db.standard_plr_objsearch(session, ' '.join(args), search_contents=False)
        # Use standard_plr_objsearch to handle duplicate/nonexistant results.
        if not target_obj:
            return

    if pobject == target_obj:
        session.msg("You can't get yourself.")
        return
    
    if not plr_is_staff and (target_obj.is_player() or target_obj.is_exit()):
        session.msg("You can't get that.")
        return
        
    if target_obj.is_room() or target_obj.is_garbage() or target_obj.is_going():
        session.msg("You can't get that.")
        return
        
    target_obj.move_to(pobject, quiet=True)
    session.msg("You pick up %s." % (target_obj.get_name(),))
    pobject.get_location().emit_to_contents("%s picks up %s." % (pobject.get_name(), target_obj.get_name()), exclude=pobject)
    
    # SCRIPT: Call the object's script's a_get() method.
    target_obj.get_scriptlink().a_get({
        "pobject": pobject
    })
            
def cmd_drop(cdat):
    """
    Drop an object from a player's inventory into their current location.
    """
    session = cdat['session']
    pobject = session.get_pobject()
    args = cdat['uinput']['splitted'][1:]
    plr_is_staff = pobject.is_staff()

    if len(args) == 0:    
        session.msg("Drop what?")
        return
    else:
        target_obj = functions_db.standard_plr_objsearch(session, ' '.join(args), search_location=False)
        # Use standard_plr_objsearch to handle duplicate/nonexistant results.
        if not target_obj:
            return

    if not pobject == target_obj.get_location():
        session.msg("You don't appear to be carrying that.")
        return
        
    target_obj.move_to(pobject.get_location(), quiet=True)
    session.msg("You drop %s." % (target_obj.get_name(),))
    pobject.get_location().emit_to_contents("%s drops %s." % (pobject.get_name(), target_obj.get_name()), exclude=pobject)

    # SCRIPT: Call the object's script's a_drop() method.
    target_obj.get_scriptlink().a_drop({
        "pobject": pobject
    })
            
def cmd_examine(cdat):
    """
    Detailed object examine command
    """
    session = cdat['session']
    pobject = session.get_pobject()
    args = cdat['uinput']['splitted'][1:]
    attr_search = False
    
    if len(args) == 0:    
        # If no arguments are provided, examine the invoker's location.
        target_obj = pobject.get_location()
    else:
        # Look for a slash in the input, indicating an attribute search.
        attr_split = args[0].split("/")
        
        # If the splitting by the "/" character returns a list with more than 1
        # entry, it's an attribute match.
        if len(attr_split) > 1:
            attr_search = True
            # Strip the object search string from the input with the
            # object/attribute pair.
            searchstr = attr_split[0]
            # Just in case there's a slash in an attribute name.
            attr_searchstr = '/'.join(attr_split[1:])
        else:
            searchstr = ' '.join(args)

        target_obj = functions_db.standard_plr_objsearch(session, searchstr)
        # Use standard_plr_objsearch to handle duplicate/nonexistant results.
        if not target_obj:
            return
            
    if attr_search:
        attr_matches = target_obj.attribute_namesearch(attr_searchstr)
        if attr_matches:
            for attribute in attr_matches:
                session.msg(attribute.get_attrline())
        else:
            session.msg("No matching attributes found.")
        # End attr_search if()
    else:
        session.msg("%s\r\n%s" % (
            target_obj.get_name(fullname=True),
            target_obj.get_description(no_parsing=True),
        ))
        session.msg("Type: %s Flags: %s" % (target_obj.get_type(), target_obj.get_flags()))
        session.msg("Owner: %s " % (target_obj.get_owner(),))
        session.msg("Zone: %s" % (target_obj.get_zone(),))
        
        for attribute in target_obj.get_all_attributes():
            session.msg(attribute.get_attrline())
        
        con_players = []
        con_things = []
        con_exits = []
        
        for obj in target_obj.get_contents():
            if obj.is_player():
                con_players.append(obj)  
            elif obj.is_exit():
                con_exits.append(obj)
            elif obj.is_thing():
                con_things.append(obj)
        
        if con_players or con_things:
            session.msg("%sContents:%s" % (ansi.ansi["hilite"], ansi.ansi["normal"],))
            for player in con_players:
                session.msg('%s' % (player.get_name(fullname=True),))
            for thing in con_things:
                session.msg('%s' % (thing.get_name(fullname=True),))
                
        if con_exits:
            session.msg("%sExits:%s" % (ansi.ansi["hilite"], ansi.ansi["normal"],))
            for exit in con_exits:
                session.msg('%s' %(exit.get_name(fullname=True),))
                
        if not target_obj.is_room():
            if target_obj.is_exit():
                session.msg("Destination: %s" % (target_obj.get_home(),))
            else:
                session.msg("Home: %s" % (target_obj.get_home(),))
                
            session.msg("Location: %s" % (target_obj.get_location(),))
    
def cmd_page(cdat):
    """
    Send a message to target user (if online).
    """
    session = cdat['session']
    pobject = session.get_pobject()
    server = cdat['server']
    args = cdat['uinput']['splitted'][1:]
    parsed_command = cdat['uinput']['parsed_command']
    # We use a dict to ensure that the list of targets is unique
    targets = dict()
    # Get the last paged person
    last_paged_dbrefs = pobject.get_attribute_value("LASTPAGED")
    # If they have paged someone before, go ahead and grab the object of
    # that person.
    if last_paged_dbrefs is not False:
        last_paged_objects = list()
        try:
            last_paged_dbref_list = [
                    x.strip() for x in last_paged_dbrefs.split(',')]
            for dbref in last_paged_dbref_list:
                if not functions_db.is_dbref(dbref):
                    raise ValueError
                last_paged_object = functions_db.dbref_search(dbref)
                if last_paged_object is not None:
                    last_paged_objects.append(last_paged_object)
        except ValueError:
            # LASTPAGED Attribute is not a list of dbrefs
            last_paged_dbrefs = False
            # Remove the invalid LASTPAGED attribute
            pobject.clear_attribute("LASTPAGED")

    # If they don't give a target, or any data to send to the target
    # then tell them who they last paged if they paged someone, if not
    # tell them they haven't paged anyone.
    if parsed_command['targets'] is None and parsed_command['data'] is None:
        if last_paged_dbrefs is not False and not last_paged_objects == list():
            session.msg("You last paged: %s." % (
                ', '.join([x.name for x in last_paged_objects])))
            return
        session.msg("You have not paged anyone.")
        return

    # Build a list of targets
    # If there are no targets, then set the targets to the last person they
    # paged.
    if parsed_command['targets'] is None:
        if not last_paged_objects == list():
            targets = dict([(target, 1) for target in last_paged_objects])
    else:
        # First try to match the entire target string against a single player
        full_target_match = functions_db.player_name_search(
                parsed_command['original_targets'])
        if full_target_match is not None:
            targets[full_target_match] = 1
        else:
            # For each of the targets listed, grab their objects and append
            # it to the targets list
            for target in parsed_command['targets']:
                # If the target is a dbref, behave appropriately
                if functions_db.is_dbref(target):
                    session.msg("Is dbref.")
                    matched_object = functions_db.dbref_search(target,
                            limit_types=[defines_global.OTYPE_PLAYER])
                    if matched_object is not None:
                        targets[matched_object] = 1
                    else:
                        # search returned None
                        session.msg("Player '%s' does not exist." % (
                                target))
                else:
                    # Not a dbref, so must be a username, treat it as such
                    matched_object = functions_db.player_name_search(
                            target)
                    if matched_object is not None:
                        targets[matched_object] = 1
                    else:
                        # search returned None
                        session.msg("Player '%s' does not exist." % (
                                target))
    data = parsed_command['data']
    sender_name = pobject.get_name(show_dbref=False)
    # Build our messages
    target_message = "%s pages: %s"
    sender_message = "You paged %s with '%s'."
    # Handle paged emotes
    if data.startswith(':'):
        data = data[1:]
        target_message = "From afar, %s %s"
        sender_message = "Long distance to %s: %s %s"
    # Handle paged emotes without spaces
    if data.startswith(';'):
        data = data[1:]
        target_message = "From afar, %s%s"
        sender_message = "Long distance to %s: %s%s"

    # We build a list of target_names for the sender_message later
    target_names = []
    for target in targets.keys():
        # Check to make sure they're connected, or a player
        if target.is_connected_plr():
            target.emit_to(target_message % (sender_name, data))
            target_names.append(target.get_name(show_dbref=False))
        else:
            session.msg("Player %s does not exist or is not online." % (
                    target.get_name(show_dbref=False)))

    if len(target_names) > 0:
        target_names_string = ', '.join(target_names)
        try:
            session.msg(sender_message % (target_names_string, sender_name, data))
        except TypeError:
            session.msg(sender_message % (target_names_string, data))
        # Now set the LASTPAGED attribute
        pobject.set_attribute("LASTPAGED", ','.join(
                ["#%d" % (x.id) for x in targets.keys()]))

def cmd_quit(cdat):
    """
    Gracefully disconnect the user as per his own request.
    """
    session = cdat['session']
    session.msg("Quitting!")
    session.handle_close()
    
def cmd_who(cdat):
    """
    Generic WHO command.
    """
    session_list = session_mgr.get_session_list()
    session = cdat['session']
    pobject = session.get_pobject()
    show_session_data = pobject.user_has_perm("genperms.see_session_data")

    # Only those with the see_session_data or superuser status can see
    # session details.
    if show_session_data:
        retval = "Player Name               On For Idle   Room    Cmds   Host\n\r"
    else:
        retval = "Player Name               On For Idle\n\r"
        
    for player in session_list:
        if not player.logged_in:
            continue
        delta_cmd = time.time() - player.cmd_last_visible
        delta_conn = time.time() - player.conn_time
        plr_pobject = player.get_pobject()

        if show_session_data:
            retval += '%-16s%9s %4s%-3s#%-6d%5d%3s%-25s\r\n' % \
                (plr_pobject.get_name(show_dbref=False)[:25].ljust(27), \
                # On-time
                functions_general.time_format(delta_conn,0), \
                # Idle time
                functions_general.time_format(delta_cmd,1), \
                # Flags
                '', \
                # Location
                plr_pobject.get_location().id, \
                player.cmd_total, \
                # More flags?
                '', \
                player.address[0])
        else:
            retval += '%-16s%9s %4s%-3s\r\n' % \
                (plr_pobject.get_name(show_dbref=False)[:25].ljust(27), \
                # On-time
                functions_general.time_format(delta_conn,0), \
                # Idle time
                functions_general.time_format(delta_cmd,1), \
                # Flags
                '')
    retval += '%d Players logged in.' % (len(session_list),)
    
    session.msg(retval)

def cmd_say(cdat):
    """
    Room-based speech command.
    """
    session = cdat['session']

    if not functions_general.cmd_check_num_args(session, cdat['uinput']['splitted'], 1, errortext="Say what?"):
        return
    
    session_list = session_mgr.get_session_list()
    pobject = session.get_pobject()
    speech = ' '.join(cdat['uinput']['splitted'][1:])
    
    players_present = [player for player in session_list if player.get_pobject().get_location() == session.get_pobject().get_location() and player != session]
    
    retval = "You say, '%s'" % (speech,)
    for player in players_present:
        player.msg("%s says, '%s'" % (pobject.get_name(show_dbref=False), speech,))
    
    session.msg(retval)

def cmd_pose(cdat):
    """
    Pose/emote command.
    """
    session = cdat['session']
    pobject = session.get_pobject()
    switches = cdat['uinput']['root_chunk'][1:]

    if not functions_general.cmd_check_num_args(session, cdat['uinput']['splitted'], 1, errortext="Do what?"):
        return
    
    session_list = session_mgr.get_session_list()
    speech = ' '.join(cdat['uinput']['splitted'][1:])
    
    if "nospace" in switches:
        sent_msg = "%s%s" % (pobject.get_name(show_dbref=False), speech)
    else:
        sent_msg = "%s %s" % (pobject.get_name(show_dbref=False), speech)
    
    players_present = [player for player in session_list if player.get_pobject().get_location() == session.get_pobject().get_location()]
    
    for player in players_present:
        player.msg(sent_msg)
    
def cmd_help(cdat):
    """
    Help system commands.
    """
    session = cdat['session']
    pobject = session.get_pobject()
    topicstr = ' '.join(cdat['uinput']['splitted'][1:])
    
    if len(topicstr) == 0:
        topicstr = "Help Index"    
    elif len(topicstr) < 2 and not topicstr.isdigit():
        session.msg("Your search query is too short. It must be at least three letters long.")
        return
        
    topics = HelpEntry.objects.find_topicmatch(pobject, topicstr)        
        
    if len(topics) == 0:
        session.msg("No matching topics found, please refine your search.")
        suggestions = HelpEntry.objects.find_topicsuggestions(pobject, topicstr)
        if len(suggestions) > 0:
            session.msg("Matching similarly named topics:")
            for result in suggestions:
                session.msg(" %s" % (result,))
                session.msg("You may type 'help <#>' to see any of these topics.")
    elif len(topics) > 1:
        session.msg("More than one match found:")
        for result in topics:
            session.msg("%3d. %s" % (result.id, result.get_topicname()))
        session.msg("You may type 'help <#>' to see any of these topics.")
    else:    
        topic = topics[0]
        session.msg("\r\n%s%s%s" % (ansi.ansi["hilite"], topic.get_topicname(), ansi.ansi["normal"]))
        session.msg(topic.get_entrytext_ingame())
